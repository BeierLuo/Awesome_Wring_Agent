import json,tempfile,threading,unittest,urllib.request,urllib.error
from pathlib import Path
from unittest.mock import patch
import server as s
import latex_project as l
from test_latex import archive,FIXTURE

class OverleafHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.http=s.ThreadingHTTPServer(('127.0.0.1',0),s.Handler);self.http.root=Path(self.temp.name).resolve()/'workspaces';self.http.config_dir=Path(self.temp.name).resolve()/'.local'
        self.folder,self.state=l.import_project(self.http.root,archive(FIXTURE),'fixture.zip');s.write_state(self.folder,self.state,None)
        threading.Thread(target=self.http.serve_forever,daemon=True).start();self.addCleanup(self.http.server_close);self.addCleanup(self.http.shutdown)
    def post(self,action,data=None,headers=None):
        req=urllib.request.Request(f'http://127.0.0.1:{self.http.server_port}/api/overleaf/'+action,data=json.dumps({'workspaceId':self.state['id'],**(data or {})}).encode(),headers=headers if headers is not None else {'Content-Type':'application/json','X-Draft-Overleaf':'1'})
        try:
            with urllib.request.urlopen(req) as response:return response.status,json.load(response)
        except urllib.error.HTTPError as error:return error.code,json.load(error)
    def test_status_and_origin_guards(self):
        self.assertEqual(self.post('status')[1]['connected'],False)
        self.assertEqual(self.post('status',headers={})[0],403)
        self.assertEqual(self.post('status',headers={'X-Draft-Overleaf':'1','Origin':'https://evil.test'})[0],403)
        self.assertEqual(self.post('status',{'workspaceId':'../../escape'})[0],400)
    def test_connection_never_returns_token(self):
        with patch('overleaf_sync.Sync.fetch',return_value=('head','refs/heads/master',({},[]))):
            code,result=self.post('connect',{'url':'https://git.overleaf.com/abcdef','token':'TEST_PRIVATE_TOKEN'})
        self.assertEqual(code,200,result);self.assertNotIn('TEST_PRIVATE_TOKEN',json.dumps(result));self.assertTrue(result['hasToken'])
        self.assertNotIn(b'TEST_PRIVATE_TOKEN',l.export_zip(self.folder));self.assertNotIn('TEST_PRIVATE_TOKEN',(self.folder/'workspace.json').read_text())
        self.assertEqual(self.post('disconnect')[1]['connected'],False)
    def test_sync_is_blocked_while_writing(self):
        with patch.dict(s.RUNS,{'fixture':object()}):
            self.assertEqual(self.post('apply',{'previewId':'missing'})[0],409)

if __name__=='__main__':unittest.main()
