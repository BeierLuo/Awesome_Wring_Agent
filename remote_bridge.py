"""Outbound-only Sites connector. No public listener, shell jobs, or cloud keys.

The local server remains authoritative. Claimed requests are never retried;
only idempotent response uploads are retried. Revision/hash guards remain in
server.py and latex_project.py.
"""
import argparse,base64,gzip,subprocess,concurrent.futures,http.client,json,os,queue,re,signal,sys,threading,time,urllib.error,urllib.parse,urllib.request
from pathlib import Path
BASE=Path(__file__).resolve().parent
MARKER='__MAC_STORED__'
HEADERS={'content-type','x-draft-agent','x-draft-settings','x-draft-library','x-draft-instructions','x-draft-latex','x-draft-gcp','x-draft-overleaf','x-draft-language','x-draft-project'}
PREFIXES=('/api/workspaces','/api/projects','/api/latex/','/api/agent-files','/api/style-library','/api/overleaf/','/api/gcp/','/api/agent/','/api/paper/')

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):raise ValueError('Unexpected redirect; connector stopped this request')

def validate_request(task):
    path=task.get('path','');parsed=urllib.parse.urlsplit(path)
    if parsed.scheme or parsed.netloc or parsed.fragment or '\\' in path or any(ord(c)<32 for c in path):raise ValueError('Invalid request path')
    if task.get('method') not in {'GET','POST'}:raise ValueError('Unsupported method')
    if parsed.path not in {'/api/health','/api/save','/api/settings','/api/remote/cloud','/api/remote/pdf-page'} and not parsed.path.startswith(PREFIXES):raise ValueError('Unsupported local endpoint')
    if parsed.path=='/api/remote/pdf-page' and task['method']!='GET':raise ValueError('Unsupported method')
    if parsed.path=='/api/settings' and task['method']!='GET':raise ValueError('API 设置请在 Mac 本地页面修改')
    if len((task.get('body') or '').encode())>60*1024*1024:raise ValueError('Request too large')
    return parsed

def strip_markers(value):
    if isinstance(value,dict):return {k:strip_markers(v) for k,v in value.items() if not(k.endswith('_key') and v==MARKER)}
    if isinstance(value,list):return [strip_markers(v) for v in value]
    return value

def redact_settings(raw):
    data=json.loads(raw)
    data['settings']={k:(MARKER if v else '') if k.endswith('_key') else v for k,v in data.get('settings',{}).items()}
    return json.dumps(data,ensure_ascii=False).encode()

class Bridge:
    def __init__(self,config):
        self.config=config;self.stop=threading.Event();self.opener=urllib.request.build_opener(NoRedirect())
        url=urllib.parse.urlsplit(config['site_url'])
        if url.scheme!='https' or url.username or url.password or url.path not in ('','/') or url.query or url.fragment:raise ValueError('Site URL must be an HTTPS origin')
        self.origin=config['site_url'].rstrip('/')
        local=urllib.parse.urlsplit(config.get('local_url','http://127.0.0.1:8768'))
        if local.scheme!='http' or local.hostname!='127.0.0.1' or local.username or local.password or local.path not in ('','/') or local.query or local.fragment:raise ValueError('Local service must be loopback HTTP')
        self.local=config.get('local_url','http://127.0.0.1:8768').rstrip('/')
    def call(self,path,data,lease=None,binary=False,retries=3,metadata=None):
        raw=data if binary else json.dumps(data).encode()
        headers={'Content-Type':'application/octet-stream' if binary else 'application/json','OAI-Sites-Authorization':'Bearer '+self.config['site_token'],'Authorization':'Bearer '+self.config['bridge_secret']}
        if lease:headers['X-Bridge-Lease']=lease
        if metadata:headers['X-Bridge-Response']=json.dumps(metadata,separators=(',',':'))
        for attempt in range(retries):
            try:
                req=urllib.request.Request(self.origin+path,data=raw,headers=headers,method='POST')
                with self.opener.open(req,timeout=40) as response:return json.load(response)
            except urllib.error.HTTPError as error:
                if error.code<500:raise RuntimeError('Site rejected connector request (HTTP '+str(error.code)+')') from None
                if attempt==retries-1:raise RuntimeError('Site temporarily unavailable') from None
            except (OSError,ValueError):
                if attempt==retries-1:raise RuntimeError('Site connection failed') from None
            self.stop.wait(1+attempt)
    def cloud_request(self,body):
        # Fixed vendor endpoints only; credentials never come from the browser.
        import server
        payload=json.loads(body);url=urllib.parse.urlsplit(payload.get('url',''));method=payload.get('method','GET')
        config=server.read_config(type('Config',(),{'config_dir':BASE/'.local'})())
        if url.scheme!='https' or url.username or url.password:raise ValueError('Invalid cloud URL')
        if url.netloc=='api.openai.com' and url.path=='/v1/responses' and not url.query and method=='POST':
            target='https://api.openai.com/v1/responses';headers={'Authorization':'Bearer '+config.get('openai_key',''),'Content-Type':'application/json'}
        elif url.netloc=='generativelanguage.googleapis.com' and re.fullmatch(r'/v1beta/models(?:/[A-Za-z0-9_.-]+:generateContent)?',url.path):
            if method not in {'GET','POST'}:raise ValueError('Invalid method')
            query=urllib.parse.parse_qs(url.query)
            if set(query)-{'pageSize','pageToken'}:raise ValueError('Invalid model query')
            target='https://generativelanguage.googleapis.com'+url.path+('?' + urllib.parse.urlencode(query,doseq=True) if query else '')
            headers={'x-goog-api-key':config.get('gemini_key',''),'Content-Type':'application/json'}
        else:raise ValueError('Unsupported cloud endpoint')
        result=server.cloud_json(target,headers,json.dumps(payload['body']).encode() if payload.get('body') is not None else None,method=method,timeout=240)
        return json.dumps(result,ensure_ascii=False).encode()
    def execute(self,task):
        ident=task['id'];lease=task['lease'];endpoint=f'/__bridge/result/{ident}/';seq=0;started=False
        def begin(status,headers):
            nonlocal started
            self.call(endpoint+'headers',{'status':status,'headers':headers},lease);started=True
        def emit(chunk):
            nonlocal seq
            self.call(endpoint+'chunk?seq='+str(seq),chunk,lease,binary=True);seq+=1
        def emit_all(raw):
            for start in range(0,len(raw),512*1024):emit(raw[start:start+512*1024])
        def complete(status,headers,raw):
            # One upload for a bounded response, instead of headers/chunks/done.
            packed=gzip.compress(raw,compresslevel=3) if len(raw)>4096 else raw
            compressed=len(packed)<len(raw)
            self.call(endpoint+'complete',packed if compressed else raw,lease,binary=True,metadata={'status':status,'headers':headers,'encoding':'gzip' if compressed else 'identity'})
        try:
            parsed=validate_request(task)
            if parsed.path=='/api/remote/pdf-page':
                # Both fixed local endpoints enforce workspace and build guards.
                # The bundle keeps image and selectable text on the same version.
                query=urllib.parse.parse_qs(parsed.query)
                if not query.get('v',[''])[0]:raise ValueError('PDF version required')
                query=urllib.parse.urlencode({k:query[k][0] for k in ('workspaceId','v','page') if k in query})
                try:
                    with self.opener.open(self.local+'/api/latex/pdf-text?'+query,timeout=30) as response:layer=json.load(response)
                    with self.opener.open(self.local+'/api/latex/pdf-page?'+query,timeout=30) as response:picture=response.read(16*1024*1024)
                    raw=json.dumps({**layer,'image':base64.b64encode(picture).decode()},ensure_ascii=False,separators=(',',':')).encode();status=200
                except urllib.error.HTTPError as error:
                    status=error.code;raw=error.read(1024*1024)
                headers={'content-type':'application/json'}
                if len(raw)<=1024*1024:complete(status,headers,raw);return
                begin(status,headers);emit_all(raw)
            elif parsed.path=='/api/remote/cloud':
                raw=self.cloud_request(task.get('body') or '{}');begin(200,{'content-type':'application/json'});emit_all(raw)
            else:
                headers={k:v for k,v in task.get('headers',{}).items() if k.lower() in HEADERS}
                body=task.get('body');raw=None
                if body is not None:raw=json.dumps(strip_markers(json.loads(body)),ensure_ascii=False).encode()
                request=urllib.request.Request(self.local+task['path'],data=raw,headers=headers,method=task['method'])
                try:response=self.opener.open(request,timeout=300)
                except urllib.error.HTTPError as error:response=error
                with response:
                    out_headers={k.lower():v for k,v in response.headers.items() if k.lower() in {'content-type','content-disposition','x-content-type-options'}}
                    if parsed.path=='/api/settings':
                        complete(response.status,out_headers,redact_settings(response.read(1024*1024)));return
                    elif 'ndjson' in out_headers.get('content-type',''):
                        begin(response.status,out_headers)
                        # Batch small deltas without waiting for the generation to finish.
                        chunks=queue.Queue(maxsize=32)
                        def read_stream():
                            try:
                                while True:
                                    piece=response.read1(65536)
                                    if not piece:break
                                    chunks.put(piece)
                            except Exception as error:chunks.put(error)
                            finally:chunks.put(None)
                        threading.Thread(target=read_stream,daemon=True).start();done=False
                        while not done:
                            batch=bytearray();until=time.monotonic()+.5
                            while len(batch)<256*1024 and time.monotonic()<until:
                                try:piece=chunks.get(timeout=max(.01,until-time.monotonic()))
                                except queue.Empty:break
                                if piece is None:done=True;break
                                if isinstance(piece,Exception):raise piece
                                batch.extend(piece)
                            if batch:emit(bytes(batch))
                    else:
                        first=response.read(1024*1024+1)
                        if len(first)<=1024*1024:complete(response.status,out_headers,first);return
                        begin(response.status,out_headers);emit_all(first)
                        while True:
                            chunk=response.read(512*1024)
                            if not chunk:break
                            emit(chunk)
            self.call(endpoint+'done',{},lease)
        except Exception:
            # Never include URL, headers, credential values, or manuscript data in logs.
            print('A request failed; reload the project to confirm its saved state.',flush=True)
            if not started:
                try:
                    begin(502,{'content-type':'application/json'});emit(json.dumps({'error':'Mac 未能完成请求。请重新载入项目确认保存状态后再试。'},ensure_ascii=False).encode());self.call(endpoint+'done',{},lease)
                except Exception:pass
            else:
                # Mark a broken stream explicitly so the browser cannot mistake a
                # partial response for a successful completed save/generation.
                try:self.call(endpoint+'failed',{},lease)
                except Exception:pass
    def run(self):
        # Refuse a different local application before enabling the bridge.
        with self.opener.open(self.local+'/api/health',timeout=5) as response:health=json.load(response)
        if health.get('app')!='paper-local' or health.get('root')!=str((BASE/'workspaces').resolve()):raise ValueError('Unexpected local workspace')
        active=set()
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            while not self.stop.is_set():
                active={f for f in active if not f.done()}
                try:
                    # Claim is intentionally not retried: a lost claim is allowed to
                    # expire, never guessed/replayed as a second mutation.
                    result=self.call('/__bridge/claim',{'slots':6-len(active)},retries=1)
                    for task in result.get('tasks',[]):active.add(pool.submit(self.execute,task))
                except Exception:print('Remote connection unavailable; retrying shortly.',flush=True)
                self.stop.wait(.2 if active else 1)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--config',type=Path,default=BASE/'.local/sites-bridge.json');args=parser.parse_args()
    os.chmod(args.config,0o600);bridge=Bridge(json.loads(args.config.read_text()))
    for signum in (signal.SIGINT,signal.SIGTERM):signal.signal(signum,lambda *_:bridge.stop.set())
    # Start the existing loopback server if it is not running after login.
    try:
        with bridge.opener.open(bridge.local+'/api/health',timeout=3) as response:json.load(response)
    except OSError:
        with (BASE/'.local/server-remote.log').open('ab') as log:
            subprocess.Popen([str(BASE/'.venv/bin/python'),str(BASE/'server.py'),'--port',str(urllib.parse.urlsplit(bridge.local).port or 8768),'--no-open'],cwd=BASE,stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
        for _ in range(30):
            try:
                with bridge.opener.open(bridge.local+'/api/health',timeout=1) as response:json.load(response)
                break
            except OSError:time.sleep(.2)
    print('Draft remote connector started.',flush=True);bridge.run()
if __name__=='__main__':main()
