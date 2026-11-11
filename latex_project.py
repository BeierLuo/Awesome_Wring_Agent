"""Local LaTeX sources, bounded ZIP import, source-backed sections and isolated builds."""
import base64, copy, hashlib, io, json, os, posixpath, re, shutil, signal, stat, subprocess, sys, tempfile, time, uuid, zipfile
from pathlib import Path, PurePosixPath
from datetime import datetime, timezone

BASE=Path(__file__).resolve().parent
MAX_ZIP=40*1024*1024
MAX_TOTAL=120*1024*1024
MAX_FILE=25*1024*1024
TEXT_EXT={'.tex','.bib','.sty','.cls','.bst','.bbx','.cbx','.def','.cfg','.txt','.md','.csv','.tsv','.tikz','.pgf','.dat'}
ALLOWED=TEXT_EXT|{'.pdf','.png','.jpg','.jpeg','.eps','.svg','.ttf','.otf','.woff','.woff2','.bbl','.ist','.fd','.clo','.dtx','.ins','.ltx','.map','.enc','.afm','.pfb','.vf','.tfm'}

def now():return datetime.now(timezone.utc).isoformat()
def digest(raw):return hashlib.sha256(raw).hexdigest()
def write(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    tmp.write_bytes(data if isinstance(data,bytes) else data.encode('utf-8'));tmp.replace(path)
def path_name(name):
    if not isinstance(name,str) or not name or len(name)>300 or '\\' in name or ':' in name or any(ord(c)<32 for c in name):raise ValueError('项目文件路径无效')
    p=PurePosixPath(name)
    if p.is_absolute() or any(x in {'..','.'} or x.startswith('.') for x in name.split('/')):raise ValueError('项目文件必须位于项目目录内')
    if p.suffix.lower() not in ALLOWED:raise ValueError('不支持的项目文件类型：'+name)
    return p.as_posix()
def source_path(folder,name):
    name=path_name(name);root=folder/'latex';p=root/name
    if root.is_symlink() or any(q.is_symlink() for q in [p,*p.parents] if q!=folder.parent):raise ValueError('项目中不支持符号链接')
    if not p.resolve().is_relative_to(root.resolve()):raise ValueError('项目路径越界')
    return p

def unzip(raw,skipped=None):
    if not 0<len(raw)<=MAX_ZIP:raise ValueError('ZIP 最大支持40 MB')
    result={};seen=set();total=0
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            if len(archive.infolist())>2000:raise ValueError('项目最多支持2000个文件')
            for item in archive.infolist():
                if item.is_dir():continue
                name=item.filename
                if name.startswith('__MACOSX/') or PurePosixPath(name).name=='.DS_Store':continue
                # Reject traversal and links even when an extension would otherwise be skipped.
                if name.startswith('/') or '\\' in name or any(p=='..' for p in name.split('/')) or ':' in name:raise ValueError('ZIP 包含越界路径')
                mode=item.external_attr>>16
                if stat.S_ISLNK(mode) or stat.S_ISFIFO(mode) or stat.S_ISCHR(mode):raise ValueError('ZIP 不支持链接或特殊文件')
                if any(p.startswith('.') for p in name.split('/')):continue
                if PurePosixPath(name).suffix.lower() not in ALLOWED:
                    if skipped is not None:skipped.append(name)
                    continue
                name=path_name(name)
                if name.casefold() in seen:raise ValueError('ZIP 包含重复文件路径')
                seen.add(name.casefold());total+=item.file_size
                if item.flag_bits&1:raise ValueError('请上传未加密的 ZIP')
                if item.file_size>MAX_FILE or total>MAX_TOTAL:raise ValueError('解压后项目过大（单文件25 MB、总计120 MB）')
                if item.file_size>1024*1024 and item.file_size>max(item.compress_size,1)*500:raise ValueError('ZIP 压缩比例异常')
                data=archive.read(item)
                if len(data)!=item.file_size:raise ValueError('ZIP 文件不完整')
                result[name]=data
    except (zipfile.BadZipFile,RuntimeError,NotImplementedError):raise ValueError('无法读取 ZIP，请检查文件是否完整或加密') from None
    # Preserve internal project paths, but remove a single enclosing export directory.
    while result and all('/' in n for n in result) and len({n.split('/')[0] for n in result})==1:
        result={n.split('/',1)[1]:v for n,v in result.items()}
    if not any(n.lower().endswith('.tex') for n in result):raise ValueError('ZIP 中没有 .tex 源文件')
    for name,data in result.items():
        if Path(name).suffix.lower() in TEXT_EXT:
            try:data.decode('utf-8')
            except UnicodeDecodeError:raise ValueError('请先将文本文件转为 UTF-8：'+name) from None
    return result

def mask_tex(text):
    chars=list(text)
    patterns=[r'(?m)(?<!\\)%[^\n]*',r'\\begin\{(?:verbatim\*?|lstlisting|minted|comment)\}[\s\S]*?\\end\{(?:verbatim\*?|lstlisting|minted|comment)\}',r'\\verb\*?([^\w\s])[^\n]*?\1']
    for pattern in patterns:
        for m in re.finditer(pattern,''.join(chars)):
            for i in range(m.start(),m.end()):
                if chars[i]!='\n':chars[i]=' '
    return ''.join(chars)

def brace_end(text,start):
    depth=0
    for i in range(start,len(text)):
        if i and text[i-1]=='\\':continue
        if text[i]=='{':depth+=1
        elif text[i]=='}':
            depth-=1
            if depth==0:return i+1
    return None

def blocks(text,name):
    masked=mask_tex(text);spans=[]
    begin=re.search(r'\\begin\s*\{document\}',masked);end_doc=re.search(r'\\end\s*\{document\}',masked)
    low=begin.end() if begin else 0;high=end_doc.start() if end_doc else len(text)
    abstracts=list(re.finditer(r'\\begin\s*\{abstract\}[\s\S]*?\\end\s*\{abstract\}',masked))
    for a in abstracts:
        if low<=a.start()<high:spans.append((a.start(),a.end(),'Abstract'))
    heads=[]
    for m in re.finditer(r'\\(chapter|section)\*?\s*(?:\[[^\]\n]*\]\s*)?\{',masked):
        if not low<=m.start()<high or any(a<=m.start()<b for a,b,_ in spans):continue
        end=brace_end(masked,m.end()-1)
        if end:heads.append((m.start(),end,text[m.end():end-1]))
    for i,(start,end,title) in enumerate(heads):
        stop=heads[i+1][0] if i+1<len(heads) else high
        upcoming=[a for a,b,_ in spans if start<a<stop]
        if upcoming:stop=min(upcoming)
        spans.append((start,stop,re.sub(r'\\[a-zA-Z]+\*?','',title).strip('{} ') or 'Section'))
    # A fragment without headings remains editable and available to the assistant as a file block.
    if not spans and text[low:high].strip():spans=[(low,high,Path(name).stem)]
    return sorted(spans)

def files(folder):
    root=folder/'latex';result={};total=0
    if root.is_symlink():raise ValueError('项目目录不能是符号链接')
    for p in sorted(root.rglob('*')):
        if p.is_symlink():raise ValueError('项目中不支持符号链接')
        if not p.is_file():continue
        name=p.relative_to(root).as_posix()
        if any(part.startswith('.') for part in p.relative_to(root).parts):continue
        if p.suffix.lower() not in ALLOWED:continue
        path_name(name);size=p.stat().st_size;total+=size
        if size>MAX_FILE or total>MAX_TOTAL:raise ValueError('本地项目文件超出大小限制')
        result[name]=p.read_bytes()
        if len(result)>2000:raise ValueError('项目文件过多')
    return result

def refresh(folder,state,force=False):
    data=files(folder);hashes={n:digest(v) for n,v in data.items()};meta=state['latex']
    if not force and meta.get('hashes')==hashes and meta.get('parserVersion')==2:return False
    old={}
    for section in state['sections']:old.setdefault((section.get('source_file'),section.get('title')),[]).append(section)
    sections=[]
    texfiles=sorted(n for n in data if n.lower().endswith('.tex'))
    candidates=[n for n in texfiles if re.search(r'\\documentclass\b',mask_tex(data[n].decode('utf-8')))]
    if meta.get('main') not in texfiles:meta['main']=next((n for n in candidates if Path(n).name in {'main.tex','paper.tex','manuscript.tex'}),next(iter(candidates),next(iter(texfiles),'')))
    # Interleave blocks and includes at their source positions. Do not flatten files on writeback.
    order=[];seen=set()
    def visit(name):
        if name in seen or name not in data:return
        seen.add(name);text=data[name].decode('utf-8');masked=mask_tex(text)
        events=[(a,0,(index,a,b,title)) for index,(a,b,title) in enumerate(blocks(text,name))]
        for m in re.finditer(r'\\(?:input|include)\b\s*(?:\{([^{}\n]+)\}|([^\s{}%\\]+))',masked):
            item=(m[1] or m[2]).strip()
            if '\\' in item:continue  # Dynamic paths require TeX expansion, not guessing.
            item=item if item.endswith('.tex') else item+'.tex'
            for base in [PurePosixPath(meta['main']).parent,PurePosixPath(name).parent,PurePosixPath('.')]:
                candidate=posixpath.normpath(str(base/item))
                if candidate in data and candidate.endswith('.tex'):
                    events.append((m.start(),1,candidate));break
        for _,kind,value in sorted(events):
            if kind:visit(value)
            else:order.append((name,*value))
    if meta['main']:visit(meta['main'])
    for name,index,a,b,title in order:
        text=data[name].decode('utf-8')
        matches=old.get((name,title),[]);previous=matches.pop(0) if matches else None;content=text[a:b]
        if previous:
            section=copy.deepcopy(previous)
            if content!=section['text']:
                section['versions'].append({'id':str(uuid.uuid4()),'at':now(),'reason':'LaTeX 源文件更新','text':content});section['pending']=None
        else:
            ident=str(uuid.uuid4());section={'id':ident,'filename':f'{len(sections)+1:03d}-{ident[:8]}.tex','versions':[{'id':str(uuid.uuid4()),'at':now(),'reason':'从 LaTeX 源码导入','text':content}],'chat':[],'input':'','pending':None}
        section.update(title=title,text=content,initialized=True,source_file=name,source_order=index,source_start=a,source_end=b,format='latex',start_page=None,end_page=None)
        sections.append(section)
    if not sections:raise ValueError('主文档中未找到可编辑正文，请在项目文件中选择正确的主 .tex 文件')
    if len(sections)>300:raise ValueError('章节块超过300个，请缩小项目')
    removed=[s for s in state['sections'] if s['id'] not in {x['id'] for x in sections}]
    if removed:write(folder/'.latex/archive'/f'{uuid.uuid4().hex}.json',json.dumps(removed,ensure_ascii=False))
    selected_id=state['sections'][state['selected']]['id'] if 0<=state.get('selected',-1)<len(state['sections']) else None
    state['sections']=sections;state['selected']=next((i for i,s in enumerate(sections) if s['id']==selected_id),-1)
    meta.update(parserVersion=2,hashes=hashes,files=[{'path':n,'size':len(v),'editable':Path(n).suffix.lower() in TEXT_EXT,'sha256':hashes[n]} for n,v in data.items()],mains=candidates or texfiles,sourceHash=digest(json.dumps({'files':hashes,'main':meta['main']},sort_keys=True).encode()))
    return True

def import_project(root,raw,name):
    skipped=[];data=unzip(raw,skipped);wid=str(uuid.uuid4());folder=root/wid
    state={'format':'paper-local-v1','id':wid,'name':Path(name or 'LaTeX project.zip').stem,'revision':1,'created':now(),'updated':now(),'sections':[],'general':{'chat':[],'input':''},'selected':-1,'pdfName':'','latex':{'main':'','hashes':{},'compiler':'tectonic','skipped':skipped}}
    try:
        for n,content in data.items():write(source_path(folder,n),content)
        write(folder/'.latex/original.zip',raw)
        refresh(folder,state,True)
    except Exception:
        shutil.rmtree(folder,ignore_errors=True);raise
    return folder,state

def apply_sections(folder,current,incoming):
    if [s['id'] for s in current['sections']]!=[s['id'] for s in incoming['sections']]:raise ValueError('LaTeX 章节结构已变化，请重新载入')
    data=files(folder);edits={}
    for before,after in zip(current['sections'],incoming['sections']):
        for key in ['source_file','source_order','source_start','source_end','format','filename']:
            if before.get(key)!=after.get(key):raise ValueError('LaTeX 来源映射不可手动更改')
        if before['text']!=after['text']:
            edits.setdefault(before['source_file'],[]).append((before['source_start'],before['source_end'],after['text'],before['text']))
    incoming['latex']=copy.deepcopy(current['latex'])
    replacements={}
    for name,changes in edits.items():
        text=data[name].decode('utf-8')
        for a,b,new,old in sorted(changes,reverse=True):
            if text[a:b]!=old:raise ValueError('源文件已变化，请重新载入后再保存')
            text=text[:a]+new+text[b:]
        replacements[name]=text
    if replacements:
        original=copy.deepcopy(incoming)
        try:
            for name,text in replacements.items():
                write(folder/'.latex/history'/uuid.uuid4().hex/name,data[name]);write(source_path(folder,name),text)
            refresh(folder,incoming,True)
        except Exception:
            for name in replacements:write(source_path(folder,name),data[name])
            incoming.clear();incoming.update(original)
            raise

def edit_file(folder,state,name,text,expected):
    p=source_path(folder,name)
    if p.suffix.lower() not in TEXT_EXT or not isinstance(text,str) or len(text.encode())>2*1024*1024:raise ValueError('仅可编辑2 MB以内的文本源文件')
    raw=p.read_bytes()
    if digest(raw)!=expected:raise ValueError('文件已被修改，请重新打开该文件')
    original=copy.deepcopy(state)
    text.encode('utf-8');write(folder/'.latex/history'/uuid.uuid4().hex/name,raw);write(p,text)
    try:refresh(folder,state,True)
    except Exception:
        write(p,raw);state.clear();state.update(original);raise

def export_zip(folder):
    result=io.BytesIO()
    with zipfile.ZipFile(result,'w',zipfile.ZIP_DEFLATED) as z:
        for n,raw in files(folder).items():z.writestr(n,raw)
    return result.getvalue()

def compiler():
    bundled=BASE/'.tools/tectonic'
    return str(bundled) if bundled.is_file() else shutil.which('tectonic')

def compile_project(folder,state,timeout=240,source_data=None):
    engine=compiler()
    if not engine:raise ValueError('未找到 Tectonic 编译器，请先安装 Tectonic 后重试')
    raw=source_data if source_data is not None else files(folder);main=state['latex']['main']
    actual_hash=digest(json.dumps({'files':{n:digest(v) for n,v in raw.items()},'main':main},sort_keys=True).encode())
    if main not in raw or not main.endswith('.tex'):raise ValueError('请选择有效主 .tex 文件')
    runid=uuid.uuid4().hex;build=folder/'.latex/builds'/runid;src=build/'source';out=build/'output';out.mkdir(parents=True)
    for n,data in raw.items():write(src/n,data)
    cache=BASE/'.tools/tectonic-cache';cache.mkdir(parents=True,exist_ok=True)
    env={k:v for k,v in os.environ.items() if k in {'PATH','LANG','LC_ALL','SYSTEMROOT'}}
    env.update(TECTONIC_CACHE_DIR=str(cache.resolve()),TECTONIC_UNTRUSTED_MODE='1',TMPDIR=str(build.resolve()))
    command=[engine,'-X','compile','--untrusted','--keep-logs','--outdir',str(out.resolve()),main]
    if sys.platform=='darwin' and Path('/usr/bin/sandbox-exec').exists():
        def q(p):return json.dumps(str(Path(p).resolve()))
        read_paths=['/System','/usr','/bin','/sbin','/Library','/opt/homebrew','/private/etc','/private/var/db','/dev',src,out,Path(engine).parent,cache,build]
        profile='(version 1)(deny default)(allow file-read-data (literal "/"))(allow file-read-metadata)(allow file-map-executable)(allow process*)(allow sysctl-read)(allow mach-lookup)(allow network-outbound)'+''.join('(allow file-read* (subpath '+q(p)+'))' for p in read_paths)+''.join('(allow file-write* (subpath '+q(p)+'))' for p in [build,cache])+'(allow file-write* (literal "/dev/null"))'
        policy=build/'compile.sb';write(policy,profile)
        command=['/usr/bin/sandbox-exec','-f',str(policy.resolve()),*command]
    elif sys.platform!='darwin':
        raise ValueError('此版本的隔离编译支持 macOS；源码编辑与 ZIP 导出仍可使用')
    logpath=build/'compiler.log';timed_out=False
    with logpath.open('wb') as log:
        process=subprocess.Popen(command,cwd=src,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        try:code=process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid,signal.SIGKILL);process.wait();code=-1;timed_out=True
    log=logpath.read_bytes()[-50000:].decode('utf-8',errors='replace')
    pdf=out/(Path(main).stem+'.pdf');ok=code==0 and pdf.is_file() and pdf.stat().st_size<=25*1024*1024 and pdf.read_bytes().startswith(b'%PDF-')
    if ok:write(folder/'.latex/compiled.pdf',pdf.read_bytes())
    result={'ok':ok,'runId':runid,'sourceHash':actual_hash,'main':main,'compiler':'tectonic','exitCode':code,'at':now(),'log':log,'error':'编译超时，请检查日志后重试' if timed_out else ('编译器退出：'+str(code) if not ok else None)}
    write(folder/'.latex/last-build.json',json.dumps(result,ensure_ascii=False))
    if ok:write(folder/'.latex/pdf-build.json',json.dumps({k:v for k,v in result.items() if k!='log'},ensure_ascii=False))
    # Keep only recent disposable build snapshots; sources and source history remain intact.
    old_builds=sorted((folder/'.latex/builds').iterdir(),key=lambda p:p.stat().st_mtime,reverse=True)
    for old in old_builds[3:]:
        if old.is_dir() and not old.is_symlink():shutil.rmtree(old,ignore_errors=True)
    return result

def build_status(folder,state):
    path=folder/'.latex/pdf-build.json';last=folder/'.latex/last-build.json'
    compiled=json.loads(path.read_text()) if path.exists() else None
    latest=json.loads(last.read_text()) if last.exists() else None
    return {'compiled':compiled,'lastBuild':latest,'stale':bool(compiled and compiled['sourceHash']!=state['latex']['sourceHash'])}
