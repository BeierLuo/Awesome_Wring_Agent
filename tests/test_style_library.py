import json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pymupdf
import style_library as lib
from writing_agent import WritingAgent

class LibraryTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name).resolve();self.library=self.root/'library';self.project=self.root/'project';self.project.mkdir()
  doc=pymupdf.open();page=doc.new_page();page.insert_text((60,60),'Prior work assumes clean labels. However, real data contain noise.\nThis gap motivates a more robust training approach.')
  self.raw=doc.tobytes();doc.close();self.paper=lib.ingest(self.raw,'reference.pdf',self.library)
 def test_named_reference_lookup_and_abstract_bypass_example_shortlist(self):
  doc=pymupdf.open();page=doc.new_page()
  page.insert_text((50,50),'HaloScope: Test paper\nXuefeng Du 2024\nAbstract\nThis is the original abstract. The final result is accurate.\nCode is available at https://example.test/code.\n1\nIntroduction\nINTRODUCTION MUST NOT LEAK.')
  item=lib.ingest(doc.tobytes(),'Xuefeng_2024_HaloScope.pdf',self.library);doc.close()
  found=lib.find_papers(self.library,'Xuefeng 2024 HALOSCOPE',[self.paper['id']])
  self.assertEqual(len(found['papers']),1)
  self.assertFalse(found['papers'][0]['in_project_scope'])
  self.assertEqual(found['papers'][0]['done'],0)
  result=lib.read_reference(self.library,item['id'],'abstract')
  self.assertEqual(result['status'],'ok');self.assertEqual(result['sources'][0]['page'],1)
  self.assertIn('Code is available',result['text']);self.assertNotIn('INTRODUCTION',result['text'])
  first=lib.read_reference(self.library,item['id'],'abstract',max_chars=30)
  rest=lib.read_reference(self.library,item['id'],'abstract',offset=first['next_offset'])
  self.assertEqual(first['text']+rest['text'],result['text'])
  self.assertEqual(lib.find_papers(self.library,'unfindable')['total'],0)
  self.assertEqual(lib.read_reference(self.library,self.paper['id'],'abstract')['status'],'section_heading_not_found')
  with self.assertRaises(ValueError):lib.read_reference(self.library,'../secret','abstract')
  with self.assertRaises(ValueError):lib.read_reference(self.library,'0'*64,'abstract')
  target={'id':'abstract','filename':'abstract.md','title':'Abstract','text':'My manuscript','initialized':True,'versions':[],'chat':[]}
  agent=WritingAgent(self.project,{'sections':[target]},target,'Find HaloScope',lambda *a:None,'reference-tools',library_root=self.library)
  calls=[{'functionCall':{'id':'a','name':'search_reference_papers','args':{'query':'HaloScope'}}},{'functionCall':{'id':'b','name':'read_reference_paper','args':{'paper_id':item['id'],'section':'abstract'}}}]
  result=agent.retrieve({'candidate':{'content':{'parts':calls}},'tool_count':0,'contents':[],'trace':[]})
  self.assertEqual(result['contents'][-1]['parts'][0]['functionResponse']['response']['output']['total'],1)
  self.assertIn('final result',result['contents'][-1]['parts'][1]['functionResponse']['response']['output']['text'])
  from paper_assistant import PaperAssistant
  researcher=PaperAssistant(agent,1)
  state=researcher.read({'output':[{'type':'function_call','call_id':'c','name':'read_reference_paper','arguments':json.dumps({'paper_id':item['id'],'section':'abstract'})}],'items':[]})
  self.assertTrue(researcher.sources)
  self.assertEqual(next(iter(researcher.sources.values()))['source'],'reference_library')

 def generated(self,body):
  source=json.loads(body['input'][0]['content'][0]['text'])['excerpts'][0]
  result={'overview':'Introduction moves from assumptions to a gap.','examples':[{'paragraph_id':source['id'],'role':'gap','section':'Introduction','purpose':'Identify a missing assumption','logic':'Prior work -> limitation -> motivation','sentence_moves':['State prior assumption','Identify gap','Motivate solution'],'wording':'Restrained contrast using However.'}]}
  return {'status':'completed','output':[{'content':[{'type':'output_text','text':json.dumps(result)}]}]}
 def analyze(self):return lib.analyze_next(self.library,self.paper['id'],self.generated,'test')
 def test_invalid_pdf_and_role_are_readable_errors(self):
  with self.assertRaises(ValueError):lib.ingest(b'%PDF- broken','bad.pdf',self.library)
  with self.assertRaises(ValueError):lib.search(self.library,role={})
 def test_dedup_exact_sources_roles_and_scope(self):
  self.assertEqual(lib.ingest(self.raw,'renamed.pdf',self.library)['id'],self.paper['id']);self.assertEqual(len(lib.catalog(self.library)),1)
  self.assertEqual(lib.search(self.library)['examples'],[])
  self.analyze();r=lib.search(self.library,[self.paper['id']],'gap');e=r['examples'][0]
  self.assertEqual(e['page'],1);self.assertIn('However',e['text']);self.assertEqual(r['pending'],[])
  self.assertEqual(lib.search(self.library,[],'gap')['examples'],[])
  self.assertEqual(lib.search(self.library,None,'method')['examples'],[])
  lib.analyze_next(self.library,self.paper['id'],lambda _:self.fail('Completed analysis must not call API'),'test')
 def test_section_scope_excludes_other_and_unknown_sections(self):
  self.analyze();paper=lib.read(self.library,self.paper['id']);example=paper['analyses'][0]['examples'][0]
  paper['analyses'][0]['examples']=[{**example,'section':section,'role':'method'} for section in ['Abstract','Introduction','方法','未知']]
  lib.write(lib.paper_path(self.library,self.paper['id'])/'paper.json',paper)
  result=lib.search(self.library,role='method',query='Introduction method',section='abstract')
  self.assertEqual([e['section'] for e in result['examples']],['Abstract'])
  self.assertEqual(result['source_section'],'abstract')
  self.assertEqual(lib.search(self.library,role='result',section='abstract')['examples'],[])
  self.assertEqual(lib.search(self.library,section='experiments')['examples'],[])
  lib.save_selection(self.project,self.library,{'paper_ids':[self.paper['id']],'role':'method'})
  self.assertEqual([e['section'] for e in lib.context(self.project,self.library,section='abstract')['examples']],['Abstract'])

 def test_abstract_writer_does_not_receive_introduction_examples(self):
  self.analyze();lib.save_selection(self.project,self.library,{'paper_ids':[self.paper['id']],'role':'gap'})
  target={'id':'abstract','filename':'abstract.md','title':'Abstract','text':'Our abstract.','initialized':True,'versions':[{'id':'v1'}],'chat':[]}
  agent=WritingAgent(self.project,{'sections':[target]},target,'polish',lambda *a:None,'scoped',library_root=self.library)
  self.assertEqual(agent.style_context['examples'],[])
  result=agent.retrieve({'candidate':{'content':{'parts':[{'functionCall':{'name':'find_style_examples','args':{'role':'gap','query':'abstract'}}}]}},'tool_count':0,'contents':[],'trace':[]})
  self.assertEqual(agent.style_results[-1]['examples'],[])
  self.assertEqual(agent.style_results[-1]['source_section'],'abstract')

 def test_every_section_isolated_in_examples_memories_and_writer_tools(self):
  import style_memory as memory
  self.analyze();paper=lib.read(self.library,self.paper['id']);example=paper['analyses'][0]['examples'][0]
  paper['analyses'][0]['examples']=[{**example,'section':title,'role':'method'} for title in [*memory.SECTIONS.values(),'Unknown']]
  lib.write(lib.paper_path(self.library,self.paper['id'])/'paper.json',paper)
  lib.save_selection(self.project,self.library,{'paper_ids':[self.paper['id']],'role':'method'})
  for section,title in memory.SECTIONS.items():
   with self.subTest(section=section):
    self.assertEqual([e['section'] for e in lib.search(self.library,section=section)['examples']],[title])
    self.assertEqual([e['section'] for e in memory.examples(self.library,None,section)],[title])
    target={'id':section,'title':title,'text':'Current facts','filename':'section.md','initialized':True,'versions':[],'chat':[]}
    agent=WritingAgent(self.project,{'sections':[target]},target,'polish',lambda *a:None,'scope-'+section,library_root=self.library)
    self.assertEqual([e['section'] for e in agent.style_context['examples']],[title])
    wrong='method' if section!='method' else 'abstract'
    state={'candidate':{'content':{'parts':[{'functionCall':{'name':'read_style_memory','args':{'author':'hongxin','section':wrong}}},{'functionCall':{'name':'recommend_writing_strategy','args':{'section':wrong,'goal':'test'}}},{'functionCall':{'name':'find_style_examples','args':{'role':'method'}}}]}},'tool_count':0,'contents':[],'trace':[]}
    output=agent.retrieve(state)['contents'][-1]['parts']
    for part in output[:2]:self.assertIn('error',part['functionResponse']['response'])
    self.assertEqual([e['section'] for e in output[2]['functionResponse']['response']['output']['examples']],[title])
  target['title']='Unclassified custom heading'
  agent=WritingAgent(self.project,{'sections':[target]},target,'polish',lambda *a:None,'unknown',library_root=self.library)
  self.assertEqual(agent.reference_section,'unknown')
  self.assertEqual(agent.style_context['examples'],[])

 def test_failed_batch_resumes_and_invented_sources_rejected(self):
  def bad(body):
   r=self.generated(body);r['output'][0]['content'][0]['text']=r['output'][0]['content'][0]['text'].replace('p1-b1','invented');return r
  with self.assertRaises(ValueError):lib.analyze_next(self.library,self.paper['id'],bad,'test')
  self.assertEqual(lib.read(self.library,self.paper['id'])['done'],0)
  self.assertEqual(self.analyze()['done'],1)
 def test_project_settings_are_independent_and_invalid_paths_rejected(self):
  self.analyze();lib.save_selection(self.project,self.library,{'paper_ids':[self.paper['id']],'role':'gap'})
  self.assertEqual(lib.context(self.project,self.library)['papers'][0]['id'],self.paper['id'])
  other=self.root/'other';other.mkdir();self.assertIsNone(lib.context(other,self.library))
  with self.assertRaises(ValueError):lib.read(self.library,'../../secret')
  with self.assertRaises(ValueError):lib.save_selection(self.project,self.library,{'paper_ids':[self.paper['id']]*4})
 def test_writer_receives_examples_not_full_pdf_and_tool_stays_scoped(self):
  self.analyze();lib.save_selection(self.project,self.library,{'paper_ids':[self.paper['id']],'role':'gap'})
  target={'id':'section','filename':'section.md','title':'Introduction','text':'OUR_CURRENT_FACTS','initialized':True,'versions':[{'id':'v1'}],'chat':[]};requests=[]
  def generate(body,timeout):
   requests.append(body)
   if len(requests)==1:return {'candidates':[{'content':{'role':'model','parts':[{'functionCall':{'name':'find_style_examples','args':{'role':'gap'}}}]},'finishReason':'STOP'}]}
   return {'candidates':[{'content':{'role':'model','parts':[{'text':'Rewritten.'}]},'finishReason':'STOP'}]}
  with patch.object(lib,'ROOT',self.library):
   result=WritingAgent(self.project,{'sections':[target]},target,'polish',generate,'style-test').run()
  payload=json.dumps(requests[0]);self.assertIn('OUR_CURRENT_FACTS',payload);self.assertIn('reference.pdf',payload);self.assertNotIn('fileData',payload)
  self.assertEqual(result['assistantCalls'],0);self.assertEqual(len(result['styleReferences']['retrieved'][0]['examples']),1)
  self.assertEqual(target['text'],'OUR_CURRENT_FACTS')

if __name__=='__main__':unittest.main()
