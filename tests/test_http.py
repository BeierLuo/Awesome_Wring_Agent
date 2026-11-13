import base64,copy,json,sys,tempfile,threading,unittest,urllib.request,urllib.error,uuid
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server as s
import pymupdf

class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.server=s.ThreadingHTTPServer(('127.0.0.1',0),s.Handler)
        self.server.root=Path(self.temp.name)/'workspaces';self.server.root.mkdir()
        self.server.config_dir=Path(self.temp.name)/'.local'
        threading.Thread(target=self.server.serve_forever,daemon=True).start()
        self.addCleanup(self.server.server_close);self.addCleanup(self.server.shutdown)
        section={'id':'abstract','title':'Abstract','filename':'01-abstract.md','text':'CURRENT ABSTRACT','initialized':True,'start_page':1,'end_page':1,'versions':[{'id':'v1','text':'CURRENT ABSTRACT'}],'chat':[]}
        self.state={'id':'paper','revision':1,'sections':[section],'general':{'chat':[]}}
        doc=pymupdf.open();page=doc.new_page();page.insert_text((50,50),'1 Abstract\nORIGINAL_PDF_TEXT '+'source '*20);raw=doc.tobytes();doc.close()
        s.write_state(self.server.root/'paper',self.state,raw)
        s.write_config(self.server,{'gemini_key':'DUMMY_SECRET','gemini_model':'models/test','openai_key':'DUMMY_OPENAI','writer_provider':'gemini'})
    def post(self,path,payload,headers=None):
        request=urllib.request.Request('http://127.0.0.1:'+str(self.server.server_port)+path,data=json.dumps(payload).encode(),headers=headers if headers is not None else {'X-Draft-Agent':'1','Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(request,timeout=20) as response:return response.status,response.read().decode()
        except urllib.error.HTTPError as e:return e.code,e.read().decode()
    def payload(self):return {'workspaceId':'paper','revision':1,'sectionId':'abstract','prompt':'Polish','runId':str(uuid.uuid4())}
    def test_latex_import_pending_and_source_save_without_cloud(self):
        import io,zipfile
        self.server.root=self.server.root.resolve()
        stream=io.BytesIO()
        original=r'\documentclass{article}\begin{document}\begin{abstract}Original.\end{abstract}\input{method}\end{document}'
        method=r'\section{Method}Preserve $x=1$ and \cite{key}.'
        with zipfile.ZipFile(stream,'w') as archive:
            archive.writestr('main.tex',original);archive.writestr('method.tex',method)
        with patch.object(s,'cloud_json',side_effect=AssertionError('No cloud call for LaTeX import or save')):
            code,data=self.post('/api/latex/import',{'name':'test.zip','zipData':base64.b64encode(stream.getvalue()).decode()},headers={'X-Draft-LaTeX':'1','Content-Type':'application/json'})
            self.assertEqual(code,200,data);result=json.loads(data);state=result['state'];folder=Path(result['folder'])
            self.assertEqual([x['title'] for x in state['sections']],['Abstract','Method'])
            self.assertTrue(all(x['initialized'] for x in state['sections']))
            section=state['sections'][1];new=method.replace('Preserve','Revised')
            section['pending']={'base':section['versions'][-1]['id'],'text':new}
            code,data=self.post('/api/save',{'state':state});self.assertEqual(code,200,data)
            self.assertEqual((folder/'latex/method.tex').read_text(),method)
            state=json.loads(data)['state'];section=state['sections'][1]
            section['text']=new;section['pending']=None
            section['versions'].append({'id':str(uuid.uuid4()),'text':new,'reason':'采用 Gemini LaTeX 修改'})
            code,data=self.post('/api/save',{'state':state});self.assertEqual(code,200,data)
            self.assertEqual((folder/'latex/method.tex').read_text(),new)
            self.assertEqual((folder/'latex/main.tex').read_text(),original)
            self.assertFalse((folder/'original.pdf').exists())
    def test_source_save_uses_file_hash_not_project_revision(self):
        import latex_project as latex
        from test_latex import archive, FIXTURE
        self.server.root=self.server.root.resolve()
        folder,state=latex.import_project(self.server.root,archive(FIXTURE),'source.zip')
        s.write_state(folder,state,None)
        original=(folder/'latex/main.tex').read_bytes()
        payload={'workspaceId':state['id'],'revision':state['revision'],
                 'path':'main.tex','sha256':latex.digest(original),
                 'text':original.decode().replace('Original abstract','Edited abstract')}
        headers={'X-Draft-LaTeX':'1','Content-Type':'application/json'}
        # An unrelated metadata save and another source edit must not block this file.
        state['revision']+=1
        state['general']['chat']=[{'role':'user','text':'Keep this conversation'}]
        s.write_state(folder,state,None)
        other=folder/'latex/sections/body.tex'
        other.write_text(other.read_text().replace('First paragraph','External paragraph'))
        code,data=self.post('/api/latex/file',payload,headers)
        self.assertEqual(code,200,data)
        current=json.loads(data)['state']
        self.assertGreater(current['revision'],payload['revision'])
        self.assertEqual(current['general']['chat'],state['general']['chat'])
        self.assertIn('External paragraph',other.read_text())
        self.assertEqual((folder/'latex/main.tex').read_text(),payload['text'])
        # A stale copy of the same file must still fail, even at the current revision.
        payload['revision']=current['revision']
        payload['text']='stale overwrite'
        code,data=self.post('/api/latex/file',payload,headers)
        self.assertEqual(code,400,data)
        self.assertIn('文件已被修改',data)
        self.assertIn('Edited abstract',(folder/'latex/main.tex').read_text())

    def test_stream_failure_reports_code_and_saves_safe_diagnostic(self):
        import gemini_stream
        payload=self.payload()
        error=gemini_stream.transport_error(TimeoutError('PRIVATE_KEY'))
        with patch('gemini_stream.generate',side_effect=error):
            code,data=self.post('/api/agent/run',payload)
        self.assertEqual(code,200)
        event=json.loads(data.splitlines()[-1])
        self.assertEqual(event['type'],'error')
        self.assertEqual(event['errorCode'],'connection_timeout')
        self.assertNotIn('PRIVATE_KEY',data)
        record=json.loads((self.server.root/'paper/.agent/runs'/payload['runId']/'error.json').read_text())
        self.assertEqual(record['code'],'connection_timeout')
        self.assertNotIn('PRIVATE_KEY',json.dumps(record))
        self.assertEqual(s.read_state(self.server.root/'paper')['sections'][0]['text'],'CURRENT ABSTRACT')

    def test_live_stream_status_is_forwarded_and_recorded(self):
        payload=self.payload()
        def stream(url,headers,body,timeout,on_text,check,on_status=None):
            on_status({'stage':'connected','chunks':0,'characters':0,'elapsed':0.2})
            on_text('Live answer')
            on_status({'stage':'completed','chunks':1,'characters':11,'elapsed':0.5})
            return {'candidates':[{'content':{'role':'model','parts':[{'text':'Live answer'}]},'finishReason':'STOP'}]}
        with patch('gemini_stream.generate',side_effect=stream):
            code,data=self.post('/api/agent/run',payload)
        self.assertEqual(code,200)
        events=[json.loads(line) for line in data.splitlines()]
        statuses=[e for e in events if e['type']=='writer_status']
        self.assertEqual([e['stage'] for e in statuses],['connected','completed'])
        self.assertEqual(statuses[0]['round'],1)
        self.assertLess(next(i for i,e in enumerate(events) if e['type']=='writer_delta'),next(i for i,e in enumerate(events) if e['type']=='result'))
        record=json.loads((self.server.root/'paper/.agent/runs'/payload['runId']/'stream-status.json').read_text())
        self.assertEqual(record['characters'],11)

    def test_stream_and_saved_credentials(self):
        requests=[]
        def cloud(url,headers,data=None,method=None,timeout=None):
            requests.append((url,headers,json.loads(data)))
            return {'candidates':[{'content':{'role':'model','parts':[{'text':'Polished.'}]},'finishReason':'STOP'}]}
        payload=self.payload()
        with patch.object(s,'cloud_json',side_effect=cloud), patch('gemini_stream.generate',side_effect=lambda url,headers,body,timeout,on_text,check,on_status=None: cloud(url,headers,json.dumps(body).encode(),timeout=timeout)):
            code,data=self.post('/api/agent/run',payload)
        self.assertEqual(code,200);events=[json.loads(line) for line in data.splitlines()]
        self.assertEqual(events[-1]['type'],'result');self.assertEqual(events[-1]['answer'],'Polished.')
        self.assertIn('generativelanguage.googleapis.com',requests[0][0]);self.assertEqual(requests[0][1]['x-goog-api-key'],'DUMMY_SECRET')
        self.assertNotIn('ORIGINAL_PDF_TEXT',json.dumps(requests[0][2]));self.assertNotIn('inlineData',data)
        for f in (self.server.root/'paper/.agent').rglob('*'):
            if f.is_file():self.assertNotIn(b'DUMMY_SECRET',f.read_bytes());self.assertNotIn(b'DUMMY_OPENAI',f.read_bytes())
        self.assertEqual(s.read_state(self.server.root/'paper')['sections'][0]['text'],'CURRENT ABSTRACT')
        with patch.object(s,'cloud_json',side_effect=AssertionError('duplicate call')):
            self.assertEqual(self.post('/api/agent/run',payload)[0],409)
    def test_two_provider_handoff(self):
        from test_agent import call,final,research_call,evidence
        requests=[];replies=[call('ask_paper_assistant',{'question':'Verify current abstract'}),research_call('read_section',{'section_id':'abstract'}),evidence(),final()]
        def cloud(url,headers,data=None,method=None,timeout=None):
            requests.append((url,headers,json.loads(data)));return replies[len(requests)-1]
        with patch.object(s,'cloud_json',side_effect=cloud), patch('gemini_stream.generate',side_effect=lambda url,headers,body,timeout,on_text,check,on_status=None: cloud(url,headers,json.dumps(body).encode(),timeout=timeout)):code,data=self.post('/api/agent/run',self.payload())
        events=[json.loads(line) for line in data.splitlines()]
        self.assertEqual(events[-1]['type'],'result',data)
        self.assertEqual(events[-1]['assistantCalls'],2)
        self.assertEqual(requests[1][0],'https://api.openai.com/v1/responses')
        self.assertEqual(requests[1][1]['Authorization'],'Bearer DUMMY_OPENAI')
        self.assertFalse(requests[1][2]['store']);self.assertEqual(requests[1][2]['model'],'gpt-4.1')
        self.assertNotIn('ORIGINAL_PDF_TEXT',json.dumps(requests))
        self.assertTrue(any(e.get('tool')=='return_evidence' for e in events))
        self.assertEqual(s.read_state(self.server.root/'paper')['sections'][0]['text'],'CURRENT ABSTRACT')
        for f in (self.server.root/'paper/.agent').rglob('*'):
            if f.is_file():self.assertNotIn(b'DUMMY_OPENAI',f.read_bytes())

    def test_local_markdown_assets_and_private_paths(self):
        base='http://127.0.0.1:'+str(self.server.server_port)
        for path in ['/markdown.js','/markdown.css','/vendor/marked.umd.js','/vendor/purify.min.js','/vendor/katex.min.js','/vendor/katex.min.css','/vendor/fonts/KaTeX_Main-Regular.woff2']:
            with urllib.request.urlopen(base+path) as response:
                self.assertEqual(response.status,200);self.assertGreater(len(response.read()),100)
        for path in ['/vendor/../.local/api-config.json','/vendor/../../server.py','/.local/api-config.json']:
            with self.assertRaises(urllib.error.HTTPError) as caught:urllib.request.urlopen(base+path)
            self.assertEqual(caught.exception.code,404)

    def test_paths_origin_revision_and_no_full_pdf_legacy_route(self):
        self.assertEqual(self.post('/api/agent/run',self.payload(),{})[0],403)
        self.assertEqual(self.post('/api/agent/run',self.payload(),{'X-Draft-Agent':'1','Origin':'https://evil.test'})[0],403)
        payload=self.payload();payload['workspaceId']='../secret';self.assertEqual(self.post('/api/agent/run',payload)[0],400)
        payload=self.payload();payload['revision']=0;self.assertEqual(self.post('/api/agent/run',payload)[0],400)
        self.assertEqual(self.post('/api/gcp/generate',{}, {'X-Draft-GCP':'1'})[0],400)
        self.assertEqual(self.post('/api/agent/cancel',{'runId':'missing'})[0],200)
    def test_targeted_pages_and_heading_index(self):
        code,data=self.post('/api/paper/context',{'workspaceId':'paper','mode':'outline'})
        self.assertEqual(code,200);self.assertEqual(json.loads(data)['page_count'],1)
        code,data=self.post('/api/paper/context',{'workspaceId':'paper','mode':'pages','start_page':1,'end_page':1})
        self.assertEqual(code,200);self.assertIn('ORIGINAL_PDF_TEXT',data);self.assertNotIn('application/pdf',data)
        self.assertEqual(self.post('/api/paper/context',{'workspaceId':'paper','mode':'pages','start_page':1,'end_page':20})[0],400)
    def test_conversation_history_survives_save_without_entering_context(self):
        from writing_agent import initial_contents
        state=copy.deepcopy(self.state)
        section=state['sections'][0]
        section.update(conversationId='active-chat',contextStart=0,chat=[{'role':'user','text':'ACTIVE_ONLY'}],
                       conversations=[{'id':'old-chat','chat':[{'role':'user','text':'ARCHIVED_ONLY'}],'input':'saved draft'}])
        code,body=self.post('/api/save',{'state':state})
        self.assertEqual(code,200,body)
        restored=s.read_state(self.server.root/'paper')
        self.assertEqual(restored['sections'][0]['conversations'],section['conversations'])
        request=json.dumps(initial_contents(restored,restored['sections'][0],'continue'))
        self.assertIn('ACTIVE_ONLY',request)
        self.assertNotIn('ARCHIVED_ONLY',request)

    def test_writer_reasoning_controls(self):
        payload=self.payload()
        payload['config']={'writer_provider':'openai','openai_writer_model':'gpt-6-astra','writer_reasoning_effort':'high'}
        prepared=s.prepare_agent(self.server,payload)
        original={'generationConfig':{'maxOutputTokens':32768}}
        with patch('openai_writer.generate',return_value={}) as generate:
            prepared[5].stream(original,30,lambda text:None,lambda:None)
            self.assertEqual(generate.call_args.args[2]['reasoningEffort'],'high')
        self.assertNotIn('reasoningEffort',original)
        payload['config']={'writer_provider':'gemini','gemini_model':'gemini-4-carbon','writer_reasoning_effort':'medium'}
        prepared=s.prepare_agent(self.server,payload)
        with patch('gemini_stream.generate',return_value={}) as generate:
            prepared[5].stream(original,30,lambda text:None,lambda:None)
            self.assertEqual(generate.call_args.args[2]['generationConfig'],{'maxOutputTokens':32768,'thinkingConfig':{'thinkingLevel':'MEDIUM'}})
        payload['config']['gemini_model']='gemini-2.5-pro'
        with self.assertRaisesRegex(ValueError,'不支持'):s.prepare_agent(self.server,payload)
        payload['config']['writer_reasoning_effort']='default'
        prepared=s.prepare_agent(self.server,payload)
        with patch('gemini_stream.generate',return_value={}) as generate:
            prepared[5].stream(original,30,lambda text:None,lambda:None)
            self.assertNotIn('thinkingConfig',generate.call_args.args[2]['generationConfig'])
        payload['config']['writer_reasoning_effort']='invalid'
        with self.assertRaisesRegex(ValueError,'无效'):s.prepare_agent(self.server,payload)

    def test_settings_fields_save_and_safe_errors(self):
        headers={'X-Draft-Settings':'1'}
        request=urllib.request.Request('http://127.0.0.1:'+str(self.server.server_port)+'/api/settings',headers=headers)
        with urllib.request.urlopen(request) as response:
            self.assertIn('openai_writer_model',json.load(response)['supportedFields'])
        code,body=self.post('/api/settings',{'openai_writer_model':'writer-test','openai_writer_models':'writer-two,writer-three','gcp_models':'gemini-extra','gemini_models':'gemini-test'},headers)
        self.assertEqual(code,200)
        self.assertEqual(s.read_config(self.server)['openai_writer_models'],'writer-two,writer-three')
        self.assertEqual(s.read_config(self.server)['openai_key'],'DUMMY_OPENAI')
        before=s.config_location(self.server).read_bytes()
        code,body=self.post('/api/settings',{'unknown':'DO_NOT_ECHO_SECRET'},headers)
        self.assertEqual(code,400)
        self.assertIn('配置字段无效',body)
        self.assertNotIn('DO_NOT_ECHO_SECRET',body)
        self.assertEqual(s.config_location(self.server).read_bytes(),before)
        with patch.object(s,'write_config',side_effect=PermissionError('PRIVATE_PATH')):
            code,body=self.post('/api/settings',{'openai_writer_model':'writer-test'},headers)
        self.assertEqual(code,500)
        self.assertIn('权限',body)
        self.assertNotIn('PRIVATE_PATH',body)

    def test_openai_writer_routing_and_independent_models(self):
        s.write_config(self.server,{'writer_provider':'openai','openai_writer_model':'writer-test','openai_model':'research-test'})
        prepared=s.prepare_agent(self.server,self.payload())
        self.assertEqual(prepared[7:9],('openai','writer-test'))
        with patch('openai_writer.generate',return_value={'ok':True}) as generate:
            prepared[5].stream({},30,lambda text:None,lambda:None)
            self.assertEqual(generate.call_args.args[:2],('DUMMY_OPENAI','writer-test'))
        with patch.object(s,'cloud_json',return_value={}) as generate:
            prepared[9]({},30)
            self.assertEqual(json.loads(generate.call_args.args[2])['model'],'research-test')
        self.assertEqual(s.read_config(self.server)['gemini_key'],'DUMMY_SECRET')

    def test_gcp_routing_and_config_preservation(self):
        config={'writer_provider':'gcp','gcp_auth':'standard_key','gcp_key':'DUMMY_GCP','gcp_project':'test-project','gcp_model':'gemini-4-argon'}
        payload=self.payload();payload['config']=config
        with patch.object(s,'cloud_json',return_value={'candidates':[{'content':{'role':'model','parts':[{'text':'OK'}]},'finishReason':'STOP'}]}) as cloud, patch('gemini_stream.generate',side_effect=lambda url,headers,body,timeout,on_text,check,on_status=None: cloud(url,headers,json.dumps(body).encode(),timeout=timeout)):
            code,data=self.post('/api/agent/run',payload)
        self.assertEqual(code,200);self.assertIn('/v1beta1/projects/test-project/locations/global/',cloud.call_args.args[0]);self.assertEqual(cloud.call_args.args[1]['x-goog-api-key'],'DUMMY_GCP')
        self.assertEqual(s.read_config(self.server)['gemini_key'],'DUMMY_SECRET')
        self.assertNotIn('gcp_key',s.read_config(self.server))

if __name__=='__main__':unittest.main()
