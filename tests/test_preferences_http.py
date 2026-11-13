import json
import urllib.request
import urllib.error
import unittest
from unittest.mock import patch
from pathlib import Path
import test_http
import server


class PreferenceHTTPTests(unittest.TestCase):
    setUp=test_http.HTTPTests.setUp
    post=test_http.HTTPTests.post
    def get(self,path,headers=None):
        req=urllib.request.Request('http://127.0.0.1:'+str(self.server.server_port)+path,headers=headers or {})
        try:
            with urllib.request.urlopen(req) as r:return r.status,json.load(r)
        except urllib.error.HTTPError as e:return e.code,json.load(e)
    def test_editor_auth_conflict_scopes_and_manuscript_unchanged(self):
        self.assertEqual(self.get('/api/preferences')[0],403)
        headers={'X-Draft-Preferences':'1'}
        code,data=self.get('/api/preferences?workspaceId=paper&sectionId=abstract',headers)
        self.assertEqual(code,200,data);self.assertEqual(data['context']['section_type'],'abstract')
        payload={'action':'save','workspaceId':'paper','sectionId':'abstract','expected':data['version'],'item':{'rule':'Avoid because','scope':'section'}}
        self.assertEqual(self.post('/api/preferences',payload,headers)[0],200)
        self.assertEqual(self.post('/api/preferences',payload,headers)[0],400)
        self.assertEqual(self.get('/api/preferences?workspaceId=../paper',headers)[0],400)
        self.assertEqual(self.post('/api/preferences',payload,{'X-Draft-Preferences':'1','Origin':'https://evil.example'})[0],403)
        self.assertEqual(self.get('/api/preferences?workspaceId=paper&sectionId=abstract',headers)[1]['effective'][0]['rule'],'Avoid because')
        self.assertEqual(self.get('/api/preferences?workspaceId=paper',headers)[1]['effective'],[])
        self.assertEqual(server.read_state(self.server.root/'paper')['revision'],1)
    def test_real_run_captures_preference_version_and_pending_not_injected(self):
        store=server.preference_store(self.server);ctx={'workspace':'paper','section':'abstract','section_type':'abstract'}
        store.mutate({'action':'save','expected':store.snapshot()['version'],'item':{'rule':'ACTIVE_PREFERENCE','scope':'global'}},ctx)
        store.learn([{'rule':'PENDING_PREFERENCE','quote':'我不喜欢这里。','scope':'section'}],'我不喜欢这里。',ctx,'proposal',store.snapshot()['version'])
        captured=[]
        def model(url,headers,body,timeout,on_text,check,on_status=None):
            captured.append(body)
            return {'candidates':[{'content':{'parts':[{'text':'A response.'}]},'finishReason':'STOP'}]}
        with patch('gemini_stream.generate',side_effect=model):
            code,raw=self.post('/api/agent/run',{'workspaceId':'paper','revision':1,'sectionId':'abstract','prompt':'Polish','runId':'pref-snapshot'})
        self.assertEqual(code,200,raw)
        result=[json.loads(line) for line in raw.splitlines() if json.loads(line)['type']=='result'][0]
        self.assertIn('ACTIVE_PREFERENCE',json.dumps(captured))
        self.assertNotIn('PENDING_PREFERENCE',json.dumps(captured))
        pref=result['context']['preferences'];self.assertEqual(len(pref['items']),1)
        saved=json.loads((self.server.root/'paper/.agent/runs/pref-snapshot/result.json').read_text())
        self.assertEqual(saved['context']['preferences'],pref)


if __name__=='__main__':unittest.main()
