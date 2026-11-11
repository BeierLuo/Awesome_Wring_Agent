#!/usr/bin/env python3
"""Local-only paper workspace with a private local API configuration file."""
import argparse, base64, copy, json, mimetypes, os, re, shutil, subprocess, sys, threading, uuid, webbrowser, urllib.request, urllib.error
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, quote, urlencode
from datetime import datetime, timezone

BASE=Path(__file__).resolve().parent
LOCK=threading.Lock()
RUNS_LOCK=threading.Lock()
RUNS={}
LATEX_BUILD_LOCK=threading.Lock()
sys.path.insert(0,str(BASE))
def now(): return datetime.now(timezone.utc).isoformat()
def atomic(path, data):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name(path.name+'.tmp')
    tmp.write_bytes(data if isinstance(data,bytes) else data.encode('utf-8'))
    os.replace(tmp,path)
def safe_id(value):
    if not isinstance(value,str) or not re.fullmatch(r'[a-zA-Z0-9-]{1,80}',value): raise ValueError('无效Project ID')
    return value

GCP_FIELDS={'gcp_auth','gcp_key','gcp_project','gcp_location','gcp_model','gcp_pdf_mode','gcp_bucket'}
CONFIG_FIELDS={'gemini_key','gemini_model','openai_key','openai_model','writer_provider'} | GCP_FIELDS
def config_location(server): return getattr(server,'config_dir',BASE/'.local')/'api-config.json'
def read_config(server):
    path=config_location(server)
    if not path.exists(): return {}
    os.chmod(path.parent,0o700);os.chmod(path,0o600)
    data=json.loads(path.read_text())
    return {k:v for k,v in data.items() if k in CONFIG_FIELDS and isinstance(v,str)}
def write_config(server,data):
    if not isinstance(data,dict) or set(data)-CONFIG_FIELDS: raise ValueError('配置字段无效')
    # Partial updates preserve existing credentials. An empty object explicitly clears settings.
    cleaned=read_config(server) if data else {}
    for k,value in data.items():
        if not isinstance(value,str) or len(value)>8192: raise ValueError('配置值无效')
        value=value.strip()
        if k.endswith('_key') and ('redacted' in value.lower() or value.startswith('<hidden')): raise ValueError('请输入真实 API Key，不要保存被遮蔽的占位符')
        cleaned[k]=value
    path=config_location(server);path.parent.mkdir(parents=True,exist_ok=True,mode=0o700);os.chmod(path.parent,0o700)
    tmp=path.with_name('api-config-'+str(uuid.uuid4())+'.tmp')
    try:
        fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'w') as f:
            json.dump(cleaned,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
        os.replace(tmp,path);os.chmod(path,0o600)
    finally:
        if tmp.exists(): tmp.unlink()


class CloudError(Exception):
    def __init__(self, message, code=502):
        super().__init__(message);self.code=code

def cloud_json(url, headers, data=None, method=None, timeout=180):
    req=urllib.request.Request(url,headers=headers,data=data,method=method)
    try:
        with urllib.request.urlopen(req,timeout=timeout) as response: return json.load(response)
    except urllib.error.HTTPError as e:
        # Do not reflect upstream bodies: they can contain credentials or paper text.
        messages={400:'请求参数不被接受，请检查认证方式、模型、地区和 PDF 大小。',401:'认证失败，请检查 GCP Key 或重新登录 ADC。',403:'权限不足，请检查 API 是否启用、账单、Key 限制和资源访问权限。',404:'未找到模型或资源，请检查项目、地区、模型 ID 以及 Key 的认证方式。',412:'对象已存在。',429:'额度不足或请求过多，请稍后重试。'}
        raise CloudError('Google Cloud（HTTP '+str(e.code)+'）：'+messages.get(e.code,'服务暂时不可用，请稍后重试。'),e.code) from None
    except (urllib.error.URLError,TimeoutError,OSError,ValueError):
        raise CloudError('无法连接 Google Cloud，或响应超时。请检查本机网络后重试。') from None

def adc_token():
    executable=shutil.which('gcloud')
    if not executable and Path('/opt/homebrew/share/google-cloud-sdk/bin/gcloud').is_file(): executable='/opt/homebrew/share/google-cloud-sdk/bin/gcloud'
    if not executable: raise ValueError('未找到 Google Cloud CLI。请安装 gcloud 并运行 gcloud auth application-default login，或在设置中改用 API Key。')
    try:
        result=subprocess.run([executable,'auth','application-default','print-access-token','--quiet'],capture_output=True,text=True,timeout=25)
    except (OSError,subprocess.TimeoutExpired): raise ValueError('无法读取 ADC 登录，请在终端重新登录 Google Cloud。') from None
    token=result.stdout.strip()
    if result.returncode or not token or any(c.isspace() for c in token): raise ValueError('ADC 登录不可用，请运行 gcloud auth application-default login 后重试。')
    return token

def gcp_connection(config):
    mode=config.get('gcp_auth') or 'express'
    model=config.get('gcp_model') or 'gemini-4-argon'
    location=config.get('gcp_location') or 'global'
    project=config.get('gcp_project','')
    if mode not in {'express','standard_key','adc'}: raise ValueError('GCP 认证方式无效')
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}',model): raise ValueError('请填写有效的 GCP 模型 ID')
    if not re.fullmatch(r'[a-z][a-z0-9-]{0,40}',location): raise ValueError('GCP 地区无效')
    if mode!='express' and not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9-]{0,62}',project): raise ValueError('请填写 Google Cloud 项目 ID（不是项目显示名称）')
    headers={'Content-Type':'application/json'}
    if mode=='adc': headers['Authorization']='Bearer '+adc_token();headers['x-goog-user-project']=project
    else:
        key=config.get('gcp_key','').strip()
        if not key or any(c.isspace() for c in key) or 'redacted' in key.lower(): raise ValueError('请填写真实的 GCP API Key')
        headers['x-goog-api-key']=key
    host='aiplatform.googleapis.com' if mode=='express' or location=='global' else location+'-aiplatform.googleapis.com'
    resource='' if mode=='express' else 'projects/'+project+'/locations/'+location+'/'
    return 'https://'+host+'/v1/'+resource+'publishers/google/models/'+model+':generateContent',headers

def gcp_request(server, payload, test=False):
    if not test: raise ValueError('写作已迁移到按需读取 Agent，请刷新页面后重试。')
    overrides=payload.get('config',{})
    if not isinstance(overrides,dict) or set(overrides)-GCP_FIELDS or any(not isinstance(v,str) or len(v)>8192 for v in overrides.values()): raise ValueError('GCP 配置无效')
    with LOCK: config={**read_config(server),**{k:v.strip() for k,v in overrides.items()}}
    url,headers=gcp_connection(config)
    body={'contents':[{'role':'user','parts':[{'text':'Reply with OK.'}]}],'generationConfig':{'maxOutputTokens':1024}}
    result=cloud_json(url,headers,json.dumps(body).encode(),'POST')
    if not result.get('candidates'): raise CloudError('已连接 GCP，但模型未返回候选回复。请检查模型权限或内容限制。')
    return {'ok':True,'model':config.get('gcp_model') or 'gemini-4-argon'}


def paper_snapshot(server,payload):
    wid=safe_id(payload.get('workspaceId'));folder=server.root/wid
    if folder.is_symlink(): raise ValueError('不支持链接到其他位置的Project')
    with LOCK:
        state=read_state(folder);validate(state)
    return folder,state


def prepare_agent(server,payload):
    from writing_agent import WritingAgent
    folder,state=paper_snapshot(server,payload)
    if payload.get('revision')!=state['revision']: raise ValueError('稿件版本已变化，请先从文件夹重载后再发送。')
    prompt=payload.get('prompt')
    if not isinstance(prompt,str) or not 1<=len(prompt.strip())<=20000: raise ValueError('消息应为 1–20000 字符')
    section_id=payload.get('sectionId')
    target=next((s for s in state['sections'] if s['id']==section_id),None) if section_id else None
    if section_id and target is None: raise ValueError('所选章节不存在')
    if target and not target.get('initialized'): raise ValueError('请先提取并核对当前章节原稿')
    overrides=payload.get('config',{})
    fields=GCP_FIELDS|{'gemini_key','gemini_model','writer_provider','openai_key','openai_model'}
    if not isinstance(overrides,dict) or set(overrides)-fields or any(not isinstance(v,str) or len(v)>8192 for v in overrides.values()): raise ValueError('模型配置无效')
    with LOCK: config={**read_config(server),**{k:v.strip() for k,v in overrides.items()}}
    provider=config.get('writer_provider') or 'gcp'
    if provider=='gcp':
        url,headers=gcp_connection(config)
        # Function-call ids and response parts are supported by this API version.
        url=url.replace('/v1/','/v1beta1/',1)
        model=config.get('gcp_model') or 'gemini-4-argon'
    elif provider=='gemini':
        key=config.get('gemini_key','');model=config.get('gemini_model','').removeprefix('models/')
        if not key or any(c.isspace() for c in key) or 'redacted' in key.lower(): raise ValueError('请填写真实的 Gemini API Key')
        if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}',model): raise ValueError('请先选择备用 Gemini 模型')
        url='https://generativelanguage.googleapis.com/v1beta/models/'+model+':generateContent'
        headers={'Content-Type':'application/json','x-goog-api-key':key}
    else: raise ValueError('写作服务无效')
    run_id=safe_id(payload.get('runId'))
    def generate(body,timeout): return cloud_json(url,headers,json.dumps(body).encode(),'POST',timeout=timeout)
    def stream(body,timeout,on_text,check):
        import gemini_stream
        try:return gemini_stream.generate(url,headers,body,timeout,on_text,check)
        except urllib.error.HTTPError as e:
            raise CloudError('Gemini 流式请求失败（HTTP '+str(e.code)+'），请检查模型权限、额度和配置。',e.code) from None
        except (urllib.error.URLError,TimeoutError,OSError):
            raise CloudError('Gemini 连接中断或等待超时；已生成内容仅供预览，当前稿未改写。') from None
    generate.stream=stream
    def assistant_generate(body,timeout):
        key=config.get('openai_key','')
        if not key or any(c.isspace() for c in key) or 'redacted' in key.lower(): raise ValueError('GPT 查证需要 OpenAI API Key，请在 API 设置中填写。')
        request={**body,'model':config.get('openai_model') or 'gpt-4.1'}
        try: return cloud_json('https://api.openai.com/v1/responses',{'Content-Type':'application/json','Authorization':'Bearer '+key},json.dumps(request).encode(),'POST',timeout=timeout)
        except CloudError as e: raise ValueError('OpenAI 资料助理请求失败（HTTP '+str(e.code)+'），请检查 Key、模型权限、额度或网络。') from None
    return WritingAgent,folder,state,target,prompt,generate,run_id,provider,model,assistant_generate


def read_state(folder):
    state=json.loads((folder/'workspace.json').read_text())
    changed=False
    if state.get('latex'):
        import latex_project
        if latex_project.refresh(folder,state):
            state['revision']+=1;state['updated']=now();write_state(folder,state,None)
        return state
    for s in state.get('sections',[]):
        path=folder/'sections'/s['filename']
        if s.get('initialized') and not path.exists(): raise ValueError('章节文件丢失：'+s['filename']+'。请先恢复该文件，避免覆盖。')
        if path.exists():
            content=path.read_text()
            if content!=s['text'] or not s.get('initialized'):
                s.update(text=content,initialized=True,pending=None)
                s['versions'].append(dict(id=str(uuid.uuid4()),at=now(),reason='外部编辑器修改',text=content))
                changed=True
    if changed:
        state['revision']+=1
        write_state(folder,state,None)
    return state

def validate(state):
    safe_id(state.get('id'))
    if not isinstance(state.get('sections'),list) or len(state['sections'])>300: raise ValueError('章节数据无效')
    filenames=set();ids=set()
    for s in state['sections']:
        safe_id(s['id'])
        if s['id'] in ids: raise ValueError('章节 ID 重复')
        ids.add(s['id'])
        name=s.get('filename','')
        if not re.fullmatch(r'[\w-]{1,100}\.(?:md|tex)',name) or name in filenames: raise ValueError('章节文件名无效或重复')
        filenames.add(name)
        if not isinstance(s.get('text'),str) or not isinstance(s.get('versions'),list) or not isinstance(s.get('chat'),list): raise ValueError('章节内容无效')
        for v in s['versions']:
            safe_id(v['id'])
            if not isinstance(v.get('text'),str): raise ValueError('版本内容无效')
    # Explicit allowlist: configuration/credentials never enter persisted data.
    allowed={'format','id','name','revision','created','updated','sections','general','selected','pdfName','latex'}
    if set(state)-allowed: raise ValueError('Project包含不支持的字段')

def write_state(folder,state,pdf_bytes):
    folder.mkdir(parents=True,exist_ok=True)
    import agent_files
    agent_files.ensure_memory(folder)
    if pdf_bytes is not None: atomic(folder/'original.pdf',pdf_bytes)
    for s in state['sections']:
        if s.get('initialized'): atomic(folder/'sections'/s['filename'],s['text'])
        for version in s['versions']:
            path=folder/'versions'/s['id']/(version['id']+('.tex' if state.get('latex') else '.md'))
            if not path.exists(): atomic(path,version['text'])
        atomic(folder/'conversations'/(s['id']+'.json'),json.dumps(s['chat'],ensure_ascii=False,indent=2))
    atomic(folder/'conversations'/'whole-paper.json',json.dumps(state.get('general',{}),ensure_ascii=False,indent=2))
    atomic(folder/'workspace.json',json.dumps(state,ensure_ascii=False,indent=2))

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def response(self,status,data):
        body=json.dumps(data,ensure_ascii=False).encode()
        self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(body)
    def allowed(self):
        host=self.headers.get('Host','')
        if host not in {f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}'}: return False
        origin=self.headers.get('Origin')
        return not origin or origin in {f'http://127.0.0.1:{self.server.server_port}',f'http://localhost:{self.server.server_port}'}
    def do_GET(self):
        if not self.allowed(): return self.response(403,{'error':'不允许跨来源访问Project'})
        path=urlparse(self.path)
        try:
            if path.path=='/api/settings':
                if self.headers.get('X-Draft-Settings')!='1': return self.response(403,{'error':'请通过本地设置页面访问'})
                with LOCK: config=read_config(self.server)
                return self.response(200,{'settings':config})
            if path.path.startswith('/api/agent-files'):
                if self.headers.get('X-Draft-Instructions')!='1':return self.response(403,{'error':'请通过 Agent 管理页面访问'})
                import agent_files
                query=parse_qs(path.query);wid=query.get('workspaceId',[''])[0];folder=None
                with LOCK:
                    if wid:
                        folder=self.server.root/safe_id(wid)
                        if folder.is_symlink() or not (folder/'workspace.json').is_file():raise ValueError('Project 不存在或已移入回收站')
                    base=getattr(self.server,'instruction_base',BASE)
                    if path.path=='/api/agent-files':
                        items=[]
                        for key,info in agent_files.CATALOG.items():
                            if info['scope']=='project' and folder is None:continue
                            data=agent_files.read_file(key,folder,base)
                            items.append({k:v for k,v in data.items() if k!='text'})
                        return self.response(200,{'items':items,'projectId':wid or None})
                    if path.path=='/api/agent-files/file':return self.response(200,agent_files.read_file(query.get('key',[''])[0],folder,base))
                    if path.path=='/api/agent-files/context':return self.response(200,agent_files.bundle('maintainer',folder,query.get('task',[''])[0],base))
                    if path.path=='/api/agent-files/memory':
                        if folder is None:raise ValueError('请先选择 Project')
                        return self.response(200,{'memory':agent_files.memory_snapshot(folder)})
                    return self.response(404,{'error':'未知 Agent 文件接口'})
            if path.path.startswith('/api/style-library'):
                if self.headers.get('X-Draft-Library')!='1':return self.response(403,{'error':'请从论文库访问'})
                import style_library as library
                query=parse_qs(path.query);root=getattr(self.server,'library_root',BASE/'style-library')
                if path.path=='/api/style-library':return self.response(200,{'items':library.catalog(root),'roles':library.ROLES,'root':str(root)})
                if path.path=='/api/style-library/strategy':
                    import style_memory as memory
                    folder=self.server.root/safe_id(query.get('workspaceId',[''])[0])
                    if folder.is_symlink() or not (folder/'workspace.json').is_file():raise ValueError('Project 不存在')
                    state=read_state(folder);target=next((s for s in state['sections'] if s['id']==query.get('sectionId',[''])[0]),None)
                    dashboard=memory.dashboard(root,folder,target.get('title','') if target else '',target)
                    return self.response(200,{'settings':memory.settings(folder),'sections':memory.SECTIONS,'authors':memory.AUTHORS,'dashboard':dashboard})
                if path.path=='/api/style-library/memory':
                    import style_memory as memory
                    return self.response(200,memory.read(root,query.get('author',[''])[0],query.get('section',[''])[0]))
                if path.path=='/api/style-library/analysis':
                    p=library.read(root,query.get('id',[''])[0])
                    return self.response(200,{'paper':library.summary(p),'overviews':[a['overview'] for a in p['analyses']]})
                if path.path=='/api/style-library/pdf':
                    raw=(library.paper_path(root,query.get('id',[''])[0])/'original.pdf').read_bytes()
                    self.send_response(200);self.send_header('Content-Type','application/pdf');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw);return
                if path.path=='/api/style-library/selection':
                    folder=self.server.root/safe_id(query.get('workspaceId',[''])[0])
                    if folder.is_symlink() or not (folder/'workspace.json').is_file():raise ValueError('Project 不存在')
                    return self.response(200,library.selected(folder))
                return self.response(404,{'error':'未知论文库接口'})
            if path.path=='/api/health': return self.response(200,{'app':'paper-local','root':str(self.server.root),'writingMode':'langgraph-on-demand'})
            if path.path in {'/api/workspaces','/api/projects'}:
                import projects
                trashed=parse_qs(path.query).get('trash',['0'])[0]=='1' and path.path=='/api/projects'
                with LOCK:items=projects.catalog(self.server.root,trashed)
                return self.response(200,{'root':str(self.server.root),'items':items})
            if path.path.startswith('/api/workspaces/'):
                wid=safe_id(path.path.split('/')[-1]);folder=self.server.root/wid
                with LOCK:
                    state=read_state(folder)
                    raw=(folder/'original.pdf').read_bytes() if (folder/'original.pdf').exists() else None
                return self.response(200,{'state':state,'pdfData':base64.b64encode(raw).decode() if raw else None,'folder':str(folder)})
            if path.path.startswith('/api/latex/'):
                import latex_project as latex
                query=parse_qs(path.query);wid=safe_id(query.get('workspaceId',[''])[0]);folder=self.server.root/wid
                with LOCK:state=read_state(folder)
                if not state.get('latex'):raise ValueError('当前不是 LaTeX 项目')
                if path.path=='/api/latex/info':return self.response(200,{'latex':state['latex'],'revision':state['revision'],'compilerAvailable':bool(latex.compiler()),**latex.build_status(folder,state)})
                if path.path=='/api/latex/file':
                    name=query.get('path',[''])[0];file=latex.source_path(folder,name)
                    if file.suffix.lower() not in latex.TEXT_EXT or file.stat().st_size>2*1024*1024:raise ValueError('该文件不可在文本编辑器中打开')
                    raw=file.read_bytes();return self.response(200,{'path':name,'text':raw.decode('utf-8'),'sha256':latex.digest(raw),'revision':state['revision']})
                if path.path in {'/api/latex/pdf-info','/api/latex/pdf-page'}:
                    import pymupdf
                    with pymupdf.open(folder/'.latex/compiled.pdf') as doc:
                        if path.path=='/api/latex/pdf-info':return self.response(200,{'pages':len(doc)})
                        page=int(query.get('page',['1'])[0])
                        if not 1<=page<=len(doc):raise ValueError('PDF 页码无效')
                        view=doc[page-1];scale=min(2,1600/max(view.rect.width,view.rect.height))
                        raw=view.get_pixmap(matrix=pymupdf.Matrix(scale,scale),alpha=False).tobytes('png');mime='image/png'
                elif path.path=='/api/latex/pdf':raw=(folder/'.latex/compiled.pdf').read_bytes();mime='application/pdf'
                elif path.path=='/api/latex/export':raw=latex.export_zip(folder);mime='application/zip'
                else:return self.response(404,{'error':'未知 LaTeX 操作'})
                self.send_response(200);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(raw)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
                if mime=='application/zip':self.send_header('Content-Disposition','attachment; filename=latex-project.zip')
                self.end_headers();self.wfile.write(raw);return
            if path.path.startswith('/api/'): return self.response(404,{'error':'不存在的接口'})
            name=path.path.lstrip('/') or 'index.html'
            if name not in {'index.html','style.css','app.js','workspace.js','workspace-core.js','workspace.css','settings.js','providers.js','markdown.js','markdown.css','latex.js','latex.css','projects.js','projects.css','agent-files.js','agent-files.css','style-library.js','style-library.css','writing-strategy.js','writing-strategy.css'} and not re.fullmatch(r'vendor/(?:marked\.umd\.js|purify\.min\.js|katex\.min\.(?:js|css)|fonts/[A-Za-z0-9_-]+\.(?:woff2?|ttf))',name): return self.response(404,{'error':'Not found'})
            raw=(BASE/'ui'/name).read_bytes();self.send_response(200);self.send_header('Content-Type',mimetypes.guess_type(name)[0] or 'application/octet-stream');self.send_header('Content-Length',str(len(raw)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(raw)
        except FileNotFoundError: self.response(404,{'error':'未找到Project文件'})
        except (ValueError,KeyError,OSError) as e: self.response(400,{'error':str(e)})
    def do_POST(self):
        if not self.allowed(): return self.response(403,{'error':'不允许跨来源写入Project'})
        route=urlparse(self.path).path
        if route=='/api/agent-files/save':
            if self.headers.get('X-Draft-Instructions')!='1':return self.response(403,{'error':'请通过 Agent 管理页面保存'})
            try:
                import agent_files
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=80000:raise ValueError('Agent 文件请求过大')
                payload=json.loads(self.rfile.read(size))
                if not isinstance(payload,dict):raise ValueError('Agent 文件请求无效')
                with LOCK:
                    folder=None
                    if payload.get('workspaceId'):
                        folder=self.server.root/safe_id(payload['workspaceId'])
                        if folder.is_symlink() or not (folder/'workspace.json').is_file():raise ValueError('Project 不存在或已移入回收站')
                    result=agent_files.save_file(payload.get('key'),payload.get('text'),payload.get('sha256'),folder,getattr(self.server,'instruction_base',BASE))
                return self.response(200,result)
            except (ValueError,KeyError,TypeError,OSError) as e:return self.response(400,{'error':str(e)})
        if route.startswith('/api/style-library/'):
            if self.headers.get('X-Draft-Library')!='1':return self.response(403,{'error':'请从论文库操作'})
            try:
                import style_library as library
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=35*1024*1024:raise ValueError('论文库请求过大')
                payload=json.loads(self.rfile.read(size));root=getattr(self.server,'library_root',BASE/'style-library')
                if not isinstance(payload,dict):raise ValueError('论文库请求格式无效')
                if route in {'/api/style-library/recommend','/api/style-library/adopt-strategy','/api/style-library/strategy-settings','/api/style-library/save-memory','/api/style-library/build-memory'}:
                    import style_memory as memory,agent_files
                    folder=None;state=None;target=None
                    if route not in {'/api/style-library/save-memory','/api/style-library/build-memory'}:
                        folder=self.server.root/safe_id(payload.get('workspaceId'))
                        with LOCK:
                            if folder.is_symlink() or not (folder/'workspace.json').is_file():raise ValueError('Project 不存在')
                            state=read_state(folder)
                        target=next((s for s in state['sections'] if s['id']==payload.get('sectionId')),None)
                    if route=='/api/style-library/strategy-settings':return self.response(200,memory.set_settings(folder,payload.get('mode'),payload.get('goal','')))
                    if route=='/api/style-library/adopt-strategy':
                        with LOCK:result=memory.adopt(folder,read_state(folder),payload.get('proposal_id'),payload.get('index'))
                        return self.response(200,result)
                    if route=='/api/style-library/save-memory':return self.response(200,memory.save(root,payload.get('author'),payload.get('section'),payload.get('text'),payload.get('sha256')))
                    config=read_config(self.server)
                    if not config.get('openai_key'):raise ValueError('请先配置 OpenAI Key')
                    def strategy_generate(body):
                        body['model']=config.get('openai_model') or 'gpt-4.1'
                        return cloud_json('https://api.openai.com/v1/responses',{'Content-Type':'application/json','Authorization':'Bearer '+config['openai_key']},json.dumps(body).encode(),'POST',timeout=180)
                    skill='synthesize_style_memory' if route.endswith('build-memory') else 'recommend_writing_strategy'
                    rules=agent_files.bundle('stylist',skill=skill,base=getattr(self.server,'instruction_base',BASE))
                    if route.endswith('build-memory'):result=memory.build(root,payload.get('author'),payload.get('section'),strategy_generate,rules['instructions'])
                    else:
                        if target is None:raise ValueError('请先选择当前章节')
                        result=memory.recommend(root,folder,state,target,payload.get('section'),payload.get('goal',''),payload.get('mode','auto'),strategy_generate,rules['instructions'])
                    return self.response(200,result)
                if route=='/api/style-library/upload':
                    result=library.ingest(base64.b64decode(payload.get('data',''),validate=True),payload.get('name','paper.pdf'),root)
                elif route=='/api/style-library/search':result=library.search(root,payload.get('paper_ids'),payload.get('role',''),payload.get('query',''))
                elif route=='/api/style-library/selection':
                    folder=self.server.root/safe_id(payload.get('workspaceId'))
                    with LOCK:
                        if folder.is_symlink() or not (folder/'workspace.json').is_file():raise ValueError('Project 不存在')
                        result=library.save_selection(folder,root,payload)
                elif route=='/api/style-library/analyze':
                    import agent_files
                    config=read_config(self.server)
                    if not config.get('openai_key'):raise ValueError('请先在 API 设置中配置 OpenAI Key')
                    rules=agent_files.bundle('stylist',skill='analyze_style',base=getattr(self.server,'instruction_base',BASE))
                    def analyze(body):
                        body['model']=config.get('openai_model') or 'gpt-4.1'
                        return cloud_json('https://api.openai.com/v1/responses',{'Content-Type':'application/json','Authorization':'Bearer '+config['openai_key']},json.dumps(body).encode(),'POST',timeout=180)
                    result=library.analyze_next(root,payload.get('paper_id'),analyze,rules['instructions'])
                else:raise ValueError('未知论文库操作')
                return self.response(200,result)
            except CloudError as e:return self.response(502,{'error':'GPT 风格分析失败（HTTP '+str(e.code)+'），已完成的批次保留，请检查额度、模型或网络后继续。'})
            except (ValueError,KeyError,TypeError,OSError) as e:return self.response(400,{'error':str(e)})
        if route.startswith('/api/projects/'):
            if self.headers.get('X-Draft-Project')!='1':return self.response(403,{'error':'请通过 Project 管理页面操作'})
            try:
                import projects
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=8192:raise ValueError('Project 请求大小无效')
                payload=json.loads(self.rfile.read(size))
                if not isinstance(payload,dict):raise ValueError('Project 请求格式无效')
                action=route.removeprefix('/api/projects/')
                if action not in {'rename','trash','restore'}:raise ValueError('未知 Project 操作')
                with LOCK,RUNS_LOCK:
                    if RUNS or LATEX_BUILD_LOCK.locked():return self.response(409,{'error':'正在写作或编译，请完成后再管理 Project'})
                    result=projects.change(self.server.root,action,payload)
                return self.response(200,result)
            except FileNotFoundError:return self.response(404,{'error':'Project 已移动或不存在，请刷新列表'})
            except (ValueError,KeyError,TypeError,OSError) as e:return self.response(400,{'error':str(e)})
        if route.startswith('/api/latex/'):
            if self.headers.get('X-Draft-LaTeX')!='1':return self.response(403,{'error':'请通过Project操作 LaTeX 项目'})
            try:
                import latex_project as latex
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=56*1024*1024:raise ValueError('请求过大或为空')
                payload=json.loads(self.rfile.read(size))
                if route=='/api/latex/import':
                    raw=base64.b64decode(payload.get('zipData',''),validate=True)
                    with LOCK:
                        folder,state=latex.import_project(self.server.root,raw,payload.get('name','project.zip'));validate(state);write_state(folder,state,None)
                    return self.response(200,{'state':state,'folder':str(folder),'pdfData':None})
                folder,state=paper_snapshot(self.server,payload)
                if not state.get('latex'):raise ValueError('当前不是 LaTeX 项目')
                if payload.get('revision')!=state['revision']:raise ValueError('源文件或Project已变化，请先重新载入')
                if route=='/api/latex/compile':
                    if not LATEX_BUILD_LOCK.acquire(blocking=False):return self.response(409,{'error':'已有项目正在编译，请稍后重试'})
                    try:
                        with LOCK:
                            state=read_state(folder)
                            source_data=latex.files(folder)
                        result=latex.compile_project(folder,copy.deepcopy(state),source_data=source_data)
                    finally:LATEX_BUILD_LOCK.release()
                    return self.response(200,result)
                with LOCK:
                    state=read_state(folder)
                    if payload.get('revision')!=state['revision']:raise ValueError('稿件版本已变化，请重新载入')
                    if route=='/api/latex/file':latex.edit_file(folder,state,payload.get('path'),payload.get('text'),payload.get('sha256'))
                    elif route=='/api/latex/main':
                        name=payload.get('main')
                        if name not in state['latex']['mains']:raise ValueError('请选择项目内的主文档')
                        state['latex']['main']=name;latex.refresh(folder,state,True)
                    else:return self.response(404,{'error':'未知 LaTeX 操作'})
                    state['revision']+=1;state['updated']=now();write_state(folder,state,None)
                return self.response(200,{'state':state,'folder':str(folder),'pdfData':None})
            except (ValueError,KeyError,TypeError,OSError) as e:return self.response(400,{'error':str(e)})
            return
        if route in {'/api/agent/run','/api/agent/cancel','/api/paper/context'}:
            if self.headers.get('X-Draft-Agent')!='1': return self.response(403,{'error':'请通过Project访问 Agent'})
            try:
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=128*1024: raise ValueError('Agent 请求大小无效')
                payload=json.loads(self.rfile.read(size))
                if not isinstance(payload,dict): raise ValueError('请求格式无效')
                if route=='/api/agent/cancel':
                    run_id=safe_id(payload.get('runId'))
                    with RUNS_LOCK:
                        event=RUNS.get(run_id)
                        if event:event.set()
                    return self.response(200,{'cancelled':bool(event)})
                if route=='/api/paper/context':
                    from paper_tools import PaperTools
                    folder,state=paper_snapshot(self.server,payload);paper=PaperTools(folder,state)
                    mode=payload.get('mode')
                    if mode=='outline': result=paper.outline()
                    elif mode=='pages':
                        start=payload.get('start_page');end=payload.get('end_page',start)
                        if isinstance(start,bool) or isinstance(end,bool) or not isinstance(start,int) or not isinstance(end,int) or end<start or end-start>=8: raise ValueError('章节提取每次支持1–8页，请分段提取')
                        pages=[]
                        for page in range(start,end+1):
                            # Extraction is an explicit user action, separate from the agent's read budget.
                            paper.pdf_pages=set()
                            value=paper.read_pdf_pages(page,page)
                            p=value['pages'][0]
                            full=paper.index()['pages'][page-1]
                            p.update(text=full['text'],next_offset=None)
                            pages.append(p)
                        if sum(len(p['text']) for p in pages)>60000: raise ValueError('章节文本过长，请缩小提取页码范围')
                        images=[]
                        for p in pages:
                            if p['needs_image']:
                                if len(images)>=2: raise ValueError('扫描页超过2页，请先为 PDF 添加可搜索文字后再提取')
                                images.append({'page':p['page'],**paper.image(p['page'])})
                        result={'pages':pages,'images':images}
                    else: raise ValueError('读取方式无效')
                    return self.response(200,result)
                prepared=prepare_agent(self.server,payload)
            except ImportError: return self.response(503,{'error':'Agent 依赖未就绪，请使用“启动写作工作区.command”重新启动。'})
            except CloudError as e: return self.response(502,{'error':str(e)})
            except (ValueError,TypeError,KeyError,OSError) as e: return self.response(400,{'error':str(e)})
            Agent,folder,state,target,prompt,generate,run_id,provider,model,assistant_generate=prepared
            with LOCK,RUNS_LOCK:
                if not (folder/'workspace.json').is_file():return self.response(409,{'error':'Project 已移入回收站，请先恢复'})
                if run_id in RUNS or (folder/'.agent'/'runs'/run_id).exists(): return self.response(409,{'error':'本轮已提交，请勿重复发送。'})
                cancel=threading.Event();RUNS[run_id]=cancel
            self.send_response(200);self.send_header('Content-Type','application/x-ndjson; charset=utf-8');self.send_header('Cache-Control','no-store');self.send_header('Connection','close');self.end_headers();self.close_connection=True
            def emit(event):
                try:self.wfile.write((json.dumps(event,ensure_ascii=False)+'\n').encode());self.wfile.flush()
                except (BrokenPipeError,ConnectionResetError,OSError): cancel.set();raise ValueError('连接已中断，Agent 已停止。') from None
            try:
                emit({'type':'progress','message':'Gemini 只读取当前章节；需要背景时向 GPT 查证。'})
                result=Agent(folder,state,target,prompt,generate,run_id,emit,cancel,assistant_generate=assistant_generate,instruction_base=getattr(self.server,'instruction_base',BASE),library_root=getattr(self.server,'library_root',BASE/'style-library')).run()
                emit({'type':'result',**result,'provider':provider,'model':model})
            except Exception as e:
                message=str(e) if isinstance(e,(ValueError,CloudError)) else 'Agent 运行未完成，请重试；当前稿未改写。'
                try:emit({'type':'error','error':message})
                except ValueError:pass
            finally:
                with RUNS_LOCK: RUNS.pop(run_id,None)
            return
        if urlparse(self.path).path in {'/api/gcp/generate','/api/gcp/test'}:
            if self.headers.get('X-Draft-GCP')!='1': return self.response(403,{'error':'请通过Project调用 GCP'})
            try:
                size=int(self.headers.get('Content-Length','0'))
                if size<=0 or size>32*1024*1024: raise ValueError('请求过大或为空')
                payload=json.loads(self.rfile.read(size))
                if not isinstance(payload,dict): raise ValueError('请求格式无效')
                result=gcp_request(self.server,payload,urlparse(self.path).path.endswith('/test'))
                return self.response(200,result)
            except CloudError as e: return self.response(502,{'error':str(e),'upstreamStatus':e.code})
            except (ValueError,TypeError,KeyError,AttributeError) as e: return self.response(400,{'error':str(e)})
            except OSError: return self.response(500,{'error':'无法读取本地配置或论文文件'})
        if urlparse(self.path).path=='/api/settings':
            if self.headers.get('X-Draft-Settings')!='1': return self.response(403,{'error':'请通过本地设置页面保存'})
            try:
                size=int(self.headers.get('Content-Length','0'))
                if size<=0 or size>40000: raise ValueError('配置请求大小无效')
                config=json.loads(self.rfile.read(size))
                with LOCK: write_config(self.server,config)
                return self.response(200,{'saved':True})
            except (ValueError,TypeError,OSError): return self.response(400,{'error':'无法保存配置，请检查输入或文件权限'})
        if urlparse(self.path).path!='/api/save': return self.response(404,{'error':'Not found'})
        try:
            size=int(self.headers.get('Content-Length','0'))
            if size<=0 or size>60*1024*1024: raise ValueError('Project请求过大')
            payload=json.loads(self.rfile.read(size));state=payload['state'];validate(state)
            raw=base64.b64decode(payload['pdfData'],validate=True) if payload.get('pdfData') else None
            if raw and (len(raw)>12*1024*1024 or b'%PDF-' not in raw[:1024]): raise ValueError('PDF 无效或超过 12 MB')
            memory=payload.get('memory')
            if memory is not None:
                import agent_files
                agent_files.validate_memory(memory)
            folder=self.server.root/state['id']
            with LOCK:
                if memory is not None and (folder/'workspace.json').exists():raise ValueError('记忆备份仅能导入为新的 Project')
                if (self.server.root/'.trash'/state['id']).exists():return self.response(409,{'error':'Project 已移入回收站，请先恢复；当前窗口不能覆盖它。'})
                if (folder/'workspace.json').exists():
                    current=read_state(folder)
                    if state.get('revision')!=current['revision']: return self.response(409,{'error':'本地文件或另一窗口已有新修改。请先导出当前备份，再点“从文件夹重载”读取最新版本。'})
                    if current.get('latex'):
                        import latex_project
                        if raw:raise ValueError('LaTeX 项目不接受原始 PDF 覆盖')
                        latex_project.apply_sections(folder,current,state)
                    elif state.get('latex'):raise ValueError('请通过 ZIP 导入创建 LaTeX 项目')
                elif state.get('revision',0)!=0 or state.get('latex'): raise ValueError('请通过 ZIP 导入创建 LaTeX 项目；新Project版本必须从0开始')
                state['revision']=state.get('revision',0)+1;state['updated']=now();write_state(folder,state,raw)
                if memory is not None:agent_files.import_memory(folder,memory)
            self.response(200,{'revision':state['revision'],'folder':str(folder),**({'state':state} if state.get('latex') else {})})
        except (ValueError,KeyError,TypeError,OSError) as e: self.response(400,{'error':str(e)})

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8768);parser.add_argument('--root',type=Path,default=BASE/'workspaces');parser.add_argument('--no-open',action='store_true');args=parser.parse_args()
    root=args.root.expanduser().resolve();root.mkdir(parents=True,exist_ok=True)
    try:
        server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
    except OSError:
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{args.port}/api/health',timeout=2) as r: running=json.load(r)
            if running.get('app')=='paper-local' and running.get('root')==str(root):
                print('Project已经启动。',flush=True)
                if not args.no_open: webbrowser.open(f'http://127.0.0.1:{args.port}/')
                return
        except Exception: pass
        raise SystemExit('端口已被占用。请关闭旧服务，或用 --port 指定其他端口。')
    server.root=root
    print(f'Local URL: http://127.0.0.1:{args.port}/\nWorkspace folder: {root}',flush=True)
    if not args.no_open: webbrowser.open(f'http://127.0.0.1:{args.port}/')
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()
if __name__=='__main__':
    local_python=BASE/'.venv'/'bin'/'python'
    if local_python.exists() and Path(sys.prefix).resolve()!=(BASE/'.venv').resolve():
        os.execv(str(local_python),[str(local_python),str(BASE/'server.py'),*sys.argv[1:]])
    main()
