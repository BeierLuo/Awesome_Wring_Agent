"""Run against the built Wrangler preview on 8787; no real project mutations."""
import base64,concurrent.futures,json,os,sys,threading,time,urllib.error,urllib.request
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from remote_bridge import Bridge
ORIGIN=os.environ.get('DRAFT_TEST_ORIGIN','http://127.0.0.1:8787')
bridge=Bridge({'site_url':'https://example.chatgpt.site','site_token':'local-test','bridge_secret':'local-test-secret'})
bridge.origin=ORIGIN
class Local(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_GET(self):
        if self.path=='/api/settings':raw=json.dumps({'settings':{'openai_key':'must-not-leak','openai_model':'test'}}).encode();mime='application/json'
        else:raw=b'%PDF-synthetic-binary\x00\xff';mime='application/pdf'
        self.send_response(200);self.send_header('Content-Type',mime);self.end_headers();self.wfile.write(raw)
    def do_POST(self):
        data=json.loads(self.rfile.read(int(self.headers.get('Content-Length',0))))
        if self.path=='/api/agent/run':
            assert 'openai_key' not in data['config'];self.send_response(200);self.send_header('Content-Type','application/x-ndjson');self.end_headers()
            for event in [{'type':'writer_delta','text':'hello'},{'type':'result','ok':True}]:self.wfile.write((json.dumps(event)+'\n').encode());self.wfile.flush();time.sleep(.2)
        else:
            self.send_response(409);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(b'{"error":"version conflict"}')
local=ThreadingHTTPServer(('127.0.0.1',0),Local);threading.Thread(target=local.serve_forever,daemon=True).start();bridge.local=f'http://127.0.0.1:{local.server_port}'
def request(path,body=None,headers=None):
    h={'oai-authenticated-user-id':'test-owner','Origin':ORIGIN,'Content-Type':'application/json'} if headers is None else headers
    req=urllib.request.Request(ORIGIN+path,data=json.dumps(body).encode() if body is not None else None,headers=h)
    try:
        with urllib.request.urlopen(req,timeout=25) as response:return response.status,response.read()
    except urllib.error.HTTPError as error:return error.code,error.read()
try:
    assert request('/api/remote/status',headers={})[0]==401
    assert request('/api/save',{},headers={'oai-authenticated-user-id':'test','Origin':'https://evil.invalid'})[0]==403
    assert request('/__bridge/claim',{'slots':1},headers={'Authorization':'Bearer wrong'})[0]==403
    bridge.call('/__bridge/claim',{'slots':0})
    with concurrent.futures.ThreadPoolExecutor() as pool:
        cases=[('/api/settings',None),('/api/latex/pdf?workspaceId=test',None),('/api/save',{'revision':0}),('/api/agent/run',{'config':{'openai_key':'__MAC_STORED__'}})]
        for path,body in cases:
            future=pool.submit(request,path,body)
            tasks=[]
            for _ in range(30):
                tasks=bridge.call('/__bridge/claim',{'slots':1})['tasks']
                if tasks:break
                time.sleep(.1)
            assert len(tasks)==1
            assert bridge.call('/__bridge/claim',{'slots':1})['tasks']==[], 'A job must not be claimed twice'
            bridge.execute(tasks[0]);code,raw=future.result()
            if path=='/api/settings':assert code==200 and b'must-not-leak' not in raw and b'__MAC_STORED__' in raw
            elif path.startswith('/api/latex/pdf'):assert raw==b'%PDF-synthetic-binary\x00\xff'
            elif path=='/api/save':assert code==409 and b'version conflict' in raw
            else:assert [json.loads(line)['type'] for line in raw.splitlines()]==['writer_delta','result']
            print('PASS',path,code)
    # Exercise the real app and Tectonic against a disposable project.
    import tempfile,io,zipfile
    import server as app,latex_project
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp).resolve();archive=io.BytesIO()
        with zipfile.ZipFile(archive,'w') as z:z.writestr('main.tex',r'\documentclass{article}\begin{document}Remote compile test.\end{document}')
        folder,state=latex_project.import_project(root,archive.getvalue(),'remote-test.zip');app.write_state(folder,state,None)
        real=ThreadingHTTPServer(('127.0.0.1',0),app.Handler);real.root=root;threading.Thread(target=real.serve_forever,daemon=True).start();bridge.local=f'http://127.0.0.1:{real.server_port}'
        def roundtrip(path,body=None):
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future=executor.submit(request,path,body,{'oai-authenticated-user-id':'test-owner','Origin':ORIGIN,'Content-Type':'application/json','X-Draft-LaTeX':'1'})
                for _ in range(50):
                    tasks=bridge.call('/__bridge/claim',{'slots':1})['tasks']
                    if tasks:break
                    time.sleep(.1)
                assert len(tasks)==1;bridge.execute(tasks[0]);return future.result()
        try:
            code,raw=roundtrip('/api/latex/compile',{'workspaceId':state['id'],'revision':state['revision']});result=json.loads(raw);assert code==200 and result['ok'],result
            query=f'?workspaceId={state["id"]}&v={result["runId"]}'
            code,raw=roundtrip('/api/latex/pdf'+query);assert code==200 and raw.startswith(b'%PDF-')
            code,raw=roundtrip('/api/latex/pdf-text'+query+'&page=1');assert code==200 and json.loads(raw)['blocks']
            code,raw=roundtrip('/api/remote/pdf-page'+query+'&page=1');bundle=json.loads(raw)
            assert code==200 and bundle['blocks'] and base64.b64decode(bundle['image']).startswith(b'\x89PNG')
            code,raw=roundtrip('/api/remote/pdf-page'+query.replace(result['runId'],'old-build')+'&page=1')
            assert code==400,'The bundle must preserve PDF build guards'
            code,raw=roundtrip('/api/latex/file',{'workspaceId':state['id'],'revision':state['revision'],'path':'main.tex','sha256':'wrong','text':'must not overwrite'})
            assert code==400 and 'Remote compile test' in (folder/'latex/main.tex').read_text()
            print('PASS real Mac compilation, generated PDF, text layer and stale-file protection')
        finally:real.shutdown();real.server_close()
finally:local.shutdown();local.server_close()
print('PASS private gate, origin guard, connector auth, unique claims, secret redaction, binary PDF, conflicts and streaming')
