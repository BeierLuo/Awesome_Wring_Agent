import base64,gzip,io,json,sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from remote_bridge import Bridge,HEADERS,MARKER,redact_settings,strip_markers,validate_request

class RemoteBridgeTests(unittest.TestCase):
    def test_small_response_one_compressed_upload_and_large_fallback(self):
        bridge=Bridge({'site_url':'https://example.chatgpt.site','site_token':'test','bridge_secret':'test'})
        for raw,complete in [(b'{"text":"'+b'example '*10000+b'"}',True),(b'x'*(1024*1024+10),False)]:
            response=io.BytesIO(raw);response.status=200;response.headers={'Content-Type':'application/json'}
            with patch.object(bridge.opener,'open',return_value=response),patch.object(bridge,'call',return_value={}) as call:
                bridge.execute({'id':'id','lease':'lease','path':'/api/latex/pdf-text?v=1','method':'GET'})
                if complete:
                    self.assertEqual(call.call_count,1);self.assertTrue(call.call_args.args[0].endswith('/complete'))
                    self.assertEqual(call.call_args.kwargs['metadata']['encoding'],'gzip')
                    self.assertEqual(gzip.decompress(call.call_args.args[1]),raw)
                else:
                    self.assertTrue(call.call_args_list[0].args[0].endswith('/headers'))
                    self.assertTrue(call.call_args_list[-1].args[0].endswith('/done'))
                    self.assertEqual(b''.join(c.args[1] for c in call.call_args_list if '/chunk?' in c.args[0]),raw)
    def test_pdf_bundle_combines_matching_local_requests(self):
        bridge=Bridge({'site_url':'https://example.chatgpt.site','site_token':'test','bridge_secret':'test'})
        layer={'width':600,'height':800,'blocks':[]};picture=b'PNG bytes'
        with patch.object(bridge.opener,'open',side_effect=[io.BytesIO(json.dumps(layer).encode()),io.BytesIO(picture)]) as read,patch.object(bridge,'call',return_value={}) as call:
            bridge.execute({'id':'id','lease':'lease','path':'/api/remote/pdf-page?workspaceId=one&v=build1&page=2','method':'GET'})
            self.assertEqual(call.call_count,1)
            data=json.loads(call.call_args.args[1])
            self.assertEqual(base64.b64decode(data['image']),picture);self.assertEqual(data['width'],600)
            for c in read.call_args_list:self.assertTrue(c.args[0].endswith('workspaceId=one&v=build1&page=2'))
    def test_project_management_header(self):
        self.assertIn("x-draft-project",HEADERS)
    def test_path_boundary(self):
        for path in ['https://evil.invalid/api/save','//evil.invalid/api/save','/api/save\\bad','/api/save\nHost: x','/etc/passwd','/api/remote/cloud#x']:
            with self.assertRaises(ValueError):validate_request({'path':path,'method':'GET'})
        validate_request({'path':'/api/latex/file?workspaceId=one&path=main.tex','method':'GET'})
        with self.assertRaises(ValueError):validate_request({'path':'/api/settings','method':'POST','body':'{}'})
    def test_credentials_stay_local(self):
        raw=json.dumps({'settings':{'openai_key':'secret-value','gcp_key':'','openai_model':'example'},'supportedFields':['openai_key']}).encode()
        result=redact_settings(raw)
        self.assertNotIn(b'secret-value',result)
        self.assertEqual(json.loads(result)['settings']['openai_key'],MARKER)
        payload={'config':{'openai_key':MARKER,'openai_model':'example'},'prompt':'Keep this'}
        self.assertEqual(strip_markers(payload),{'config':{'openai_model':'example'},'prompt':'Keep this'})
    def test_cloud_url_is_not_arbitrary(self):
        bridge=Bridge({'site_url':'https://example.chatgpt.site','site_token':'test','bridge_secret':'test'})
        with patch('server.read_config',return_value={'openai_key':'test-key'}):
            for url in ['http://api.openai.com/v1/responses','https://evil.invalid/v1/responses','https://api.openai.com/v1/responses?key=x','https://api.openai.com.evil.invalid/v1/responses']:
                with self.assertRaises(ValueError):bridge.cloud_request(json.dumps({'url':url,'method':'POST'}))
            with patch('server.cloud_json',return_value={'ok':True}) as call:
                bridge.cloud_request(json.dumps({'url':'https://api.openai.com/v1/responses','method':'POST','body':{'model':'test'}}))
                self.assertEqual(call.call_args.args[2],b'{"model": "test"}')
                self.assertEqual(call.call_args.args[1]['Authorization'],'Bearer test-key')
    def test_no_redirect_or_non_loopback_origin(self):
        for local in ['http://example.com','http://127.0.0.1@evil.invalid','http://127.0.0.1:8768/other']:
            with self.assertRaises(ValueError):Bridge({'site_url':'https://example.chatgpt.site','local_url':local})

if __name__=='__main__':unittest.main()
