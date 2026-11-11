import copy,json,shutil,tempfile,unittest,urllib.request,urllib.error
from pathlib import Path
import test_agent as fixtures
import test_http as http_fixture
import agent_files as af
import server
from writing_agent import WritingAgent

class AgentFileTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name);self.base=self.root/'app';self.base.mkdir();self.folder=self.root/'project';self.folder.mkdir()
        for name in ['agents','skills']:shutil.copytree(af.BASE/name,self.base/name)
        self.state={'id':'test','sections':[],'general':{'chat':[]}}
    def test_manual_memory_and_roles_reach_model_and_hot_reload(self):
        af.ensure_memory(self.folder);af.write(self.folder/'memory/preferences.md','MEMORY_ONE: use British English.')
        role=self.base/'agents/writer/AGENT.md';role.write_text(role.read_text()+'\nWRITER_MARKER_ONE')
        skill=self.base/'skills/ask_paper_assistant/SKILL.md';skill.write_text(skill.read_text()+'\nWRITER_SKILL_MARKER')
        requests=[]
        def model(body,timeout):requests.append(copy.deepcopy(body));return fixtures.final()
        WritingAgent(self.folder,self.state,None,'Polish',model,'first',instruction_base=self.base).run()
        encoded=json.dumps(requests[0]);self.assertIn('WRITER_MARKER_ONE',encoded);self.assertIn('WRITER_SKILL_MARKER',encoded);self.assertIn('MEMORY_ONE',encoded);self.assertNotIn('read_pdf_pages/SKILL.md',encoded)
        role.write_text(role.read_text().replace('WRITER_MARKER_ONE','WRITER_MARKER_TWO'));af.write(self.folder/'memory/preferences.md','MEMORY_TWO')
        WritingAgent(self.folder,self.state,None,'Polish',model,'second',instruction_base=self.base).run()
        self.assertIn('WRITER_MARKER_TWO',json.dumps(requests[1]));self.assertIn('MEMORY_TWO',json.dumps(requests[1]));self.assertNotIn('MEMORY_ONE',json.dumps(requests[1]))
        other=self.root/'other';other.mkdir();WritingAgent(other,self.state,None,'Polish',model,'third',instruction_base=self.base).run()
        self.assertNotIn('MEMORY_TWO',json.dumps(requests[2]))
    def test_running_agent_keeps_snapshot_and_helper_receives_memory(self):
        af.ensure_memory(self.folder);af.write(self.folder/'memory/decisions.md','CONFIRMED_DECISION')
        role=self.base/'agents/researcher/AGENT.md';role.write_text(role.read_text()+'\nRESEARCH_OLD')
        captured=[];calls=[]
        def writer(body,timeout):
            calls.append(body)
            if len(calls)==1:
                role.write_text(role.read_text().replace('RESEARCH_OLD','RESEARCH_NEW'));af.write(self.folder/'memory/decisions.md','LATER_DECISION')
                return fixtures.call('ask_paper_assistant',{'question':'Check a fact'})
            return fixtures.final()
        def researcher(body,timeout):
            captured.append(body)
            return {'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':json.dumps({'answer':'No evidence','source_ids':[],'image_pages':[],'conflicts':[],'missing_information':['fact']})}]}]}
        WritingAgent(self.folder,self.state,None,'Check',writer,'snapshot',assistant_generate=researcher,instruction_base=self.base).run()
        self.assertIn('RESEARCH_OLD',captured[0]['instructions']);self.assertNotIn('RESEARCH_NEW',captured[0]['instructions'])
        self.assertIn('CONFIRMED_DECISION',json.dumps(captured[0]['input']));self.assertNotIn('LATER_DECISION',json.dumps(captured[0]['input']))
        self.assertIn('read_pdf_pages/SKILL.md',captured[0]['instructions'])
    def test_save_conflict_history_and_exact_allowlist(self):
        key='memory/paper.md';before=af.read_file(key,self.folder,self.base)
        updated=af.save_file(key,'Research question',before['sha256'],self.folder,self.base)
        self.assertEqual(updated['text'],'Research question');self.assertTrue(list((self.folder/'.agent/memory-history').rglob('paper.md')))
        with self.assertRaisesRegex(ValueError,'修改'):af.save_file(key,'overwrite',before['sha256'],self.folder,self.base)
        for bad in ['../server.py','.local/api-config.json','memory/../paper.md']:
            with self.assertRaises(ValueError):af.read_file(bad,self.folder,self.base)
        with self.assertRaises(ValueError):af.save_file(key,'x'*2001,updated['sha256'],self.folder,self.base)
    def test_symlinks_missing_files_and_task_scope(self):
        key='agents/writer/AGENT.md';p=self.base/key;p.unlink();p.symlink_to(af.BASE/key)
        with self.assertRaises(ValueError):af.read_file(key,base=self.base)
        p.unlink()
        with self.assertRaisesRegex(ValueError,'缺少'):af.bundle('writer',base=self.base)
        with self.assertRaises(ValueError):af.bundle('writer',skill='read_pdf_pages',base=self.base)
    def test_maintainer_only_loads_selected_skill(self):
        value=af.bundle('maintainer',self.folder,'extract_section',self.base)
        self.assertIn('extract_section/SKILL.md',value['instructions']);self.assertNotIn('apply_revision/SKILL.md',value['instructions']);self.assertEqual(len(value['memory']),3)

class AgentFileHTTPTests(unittest.TestCase):
    setUp=http_fixture.HTTPTests.setUp
    post=http_fixture.HTTPTests.post
    def get(self,path,headers=None):
        req=urllib.request.Request('http://127.0.0.1:'+str(self.server.server_port)+path,headers=headers or {})
        try:
            with urllib.request.urlopen(req) as r:return r.status,json.load(r)
        except urllib.error.HTTPError as e:return e.code,json.load(e)
    def test_access_bounds_context_and_memory_backup_restore(self):
        headers={'X-Draft-Instructions':'1'}
        self.assertEqual(self.get('/api/agent-files')[0],403)
        code,data=self.get('/api/agent-files?workspaceId=paper',headers);self.assertEqual(code,200);self.assertEqual(len(data['items']),20)
        self.assertNotIn('DUMMY_SECRET',json.dumps(data))
        self.assertEqual(self.get('/api/agent-files/file?key=.local%2Fapi-config.json',headers)[0],400)
        code,context=self.get('/api/agent-files/context?workspaceId=paper&task=apply_revision',headers);self.assertEqual(code,200);self.assertIn('apply_revision/SKILL.md',context['instructions'])
        state=copy.deepcopy(self.state);state.update(id='memory-import',revision=0)
        memory={'paper.md':'PAPER_MEMORY','preferences.md':'PREFERENCE','decisions.md':'DECISION'}
        code,_=self.post('/api/save',{'state':state,'memory':memory});self.assertEqual(code,200)
        code,data=self.get('/api/agent-files/memory?workspaceId=memory-import',headers);self.assertEqual(data['memory'],memory)
        self.assertEqual(self.post('/api/save',{'state':self.state,'memory':memory})[0],400)
        self.assertEqual(self.get('/api/agent-files?workspaceId=../paper',headers)[0],400)
    def test_memory_update_checks_sha_without_mutating_manuscript(self):
        headers={'X-Draft-Instructions':'1'};key='memory/preferences.md';code,before=self.get('/api/agent-files/file?workspaceId=paper&key='+key,headers)
        payload={'workspaceId':'paper','key':key,'text':'Use concise language.','sha256':before['sha256']}
        self.assertEqual(self.post('/api/agent-files/save',payload,headers)[0],200)
        self.assertEqual(self.post('/api/agent-files/save',payload,headers)[0],400)
        self.assertEqual(server.read_state(self.server.root/'paper')['revision'],1)
        self.assertEqual(self.post('/api/agent-files/save',payload)[0],403)

if __name__=='__main__':unittest.main()
