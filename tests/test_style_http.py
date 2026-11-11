import base64,io,json,sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import test_http
import style_library as lib

class StyleHTTPTests(unittest.TestCase):
 setUp=test_http.HTTPTests.setUp
 post=test_http.HTTPTests.post
 def test_upload_search_selection_permissions_and_isolation(self):
  self.server.library_root=self.server.root.parent/'library'
  headers={'X-Draft-Library':'1','Content-Type':'application/json'}
  raw=(self.server.root/'paper/original.pdf').read_bytes();payload={'name':'reference.pdf','data':base64.b64encode(raw).decode()}
  code,data=self.post('/api/style-library/upload',payload);self.assertEqual(code,403)
  with patch.object(test_http.s,'cloud_json',side_effect=AssertionError('Import/search must be local')):
   code,data=self.post('/api/style-library/upload',payload,headers);self.assertEqual(code,200,data);pid=json.loads(data)['id']
   code,data=self.post('/api/style-library/upload',payload,headers);self.assertEqual(json.loads(data)['id'],pid)
   code,data=self.post('/api/style-library/search',{'role':'gap'},headers);self.assertEqual(code,200);self.assertEqual(json.loads(data)['examples'],[])
   code,data=self.post('/api/style-library/selection',{'workspaceId':'paper','paper_ids':[pid],'role':'gap'},headers);self.assertEqual(code,200,data)
   self.assertEqual(lib.selected(self.server.root/'paper')['paper_ids'],[pid])
   code,data=self.post('/api/style-library/selection',{'workspaceId':'missing','paper_ids':[pid]},headers);self.assertEqual(code,400)
   code,data=self.post('/api/style-library/search',{'paper_ids':['../../secret']},headers);self.assertEqual(code,400)
