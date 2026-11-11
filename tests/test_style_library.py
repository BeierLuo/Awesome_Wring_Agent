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
