import copy,json,tempfile,unittest,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import style_memory as m,style_library as l
from unittest.mock import patch

class StyleMemoryTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name);self.folder=self.root/'project';self.folder.mkdir();self.library=self.root/'library'
  self.target={'id':'intro','title':'Introduction','text':'Current manuscript facts','initialized':True,'versions':[{'id':'v1'}]};self.state={'sections':[self.target]}
  self.source={'source_id':'s1','paper_id':'p1','paper':'Paper A','page':2,'text':'Original','role':'gap','section':'Introduction','purpose':'Motivate','logic':'Gap -> solution','wording':'Restrained','sentence_moves':[]}
 def test_small_section_files_history_and_conflict(self):
  before=m.read(self.library,'hongxin','method');m.save(self.library,'hongxin','method','A method rule',before['sha256'])
  self.assertEqual(m.read(self.library,'hongxin','introduction')['text'],'')
  with self.assertRaises(ValueError):m.save(self.library,'hongxin','method','Conflict',before['sha256'])
  after=m.read(self.library,'hongxin','method');m.save(self.library,'hongxin','method','Updated',after['sha256'])
  self.assertTrue(list((self.library/'memory/history').rglob('*.md')))
  with self.assertRaises(ValueError):m.read(self.library,'../../secrets','method')
 def test_dashboard_is_navigation_not_full_memory(self):
  r=m.read(self.library,'hongxin','introduction');m.save(self.library,'hongxin','introduction','DO_NOT_AUTOLOAD_RULE_BODY',r['sha256'])
  d=m.dashboard(self.library,self.folder,'Introduction',self.target)
  self.assertNotIn('DO_NOT_AUTOLOAD_RULE_BODY',json.dumps(d));self.assertEqual(d['current_section'],'introduction')
  m.set_settings(self.folder,'off','');self.assertIsNone(m.dashboard(self.library,self.folder,'Introduction'))
 def test_source_validation_and_conditional_rule_rendering(self):
  rule={'summary':'Sample tendency','rules':[{'rule':'Mechanism first','when':'Evidence supports mechanism','avoid':'Unsupported causal claims','source_ids':['s1']}],'uncertainties':['May reflect coauthors.']}
  with patch.object(m,'examples',return_value=[self.source]),patch.object(m,'json_result',return_value=rule):
   result=m.build(self.library,'hongxin','method',None,'rules')
  self.assertIn('Paper A 第 2 页 [s1]',result['text']);self.assertIn('Evidence supports',result['text'])
  rule['rules'][0]['source_ids']=['invented']
  with patch.object(m,'examples',return_value=[self.source]),patch.object(m,'json_result',return_value=rule):
   with self.assertRaises(ValueError):m.build(self.library,'hongxin','method',None,'rules')
 def test_candidates_persist_but_require_version_checked_adoption(self):
  option={'title':'Mechanism first','author':'hongxin','hook':'Hypothesis to verify','contribution_framing':'Simple correction','paragraph_plan':['Problem','Mechanism','Contribution'],'why_fit':'Fits supplied evidence','risks':['Verify mechanism'],'paper_ids':['p1'],'source_ids':['s1']}
  result={'diagnosis':'Two possible routes','missing_information':[],'options':[copy.deepcopy(option),copy.deepcopy(option)]}
  with patch.object(m,'examples',return_value=[self.source]),patch.object(l,'catalog',return_value=[{'id':'p1','name':'HongxinWei_Paper.pdf'}]),patch.object(l,'read',return_value={'analyses':[{'overview':'A compact correction'}]}),patch.object(m,'json_result',return_value=result):
   proposal=m.recommend(self.library,self.folder,self.state,self.target,'introduction','Plan hook','hongxin',None,'rules')
  self.assertFalse(m.plan_path(self.folder,'introduction').exists())
  self.assertTrue(m.plan_path(self.folder,'introduction').with_name('introduction-proposal.json').exists())
  self.target['versions'].append({'id':'v2'})
  with self.assertRaises(ValueError):m.adopt(self.folder,self.state,proposal['id'],0)
  self.target['versions'].pop();chosen=m.adopt(self.folder,self.state,proposal['id'],1)
  self.assertEqual(chosen['option']['title'],'Mechanism first');self.assertEqual(self.target['text'],'Current manuscript facts')
  self.assertEqual(l.selected(self.folder)['paper_ids'],[])
  self.assertEqual(m.dashboard(self.library,self.folder,'Introduction',self.target)['selected_plan']['option']['paper_ids'],['p1'])
  other={**self.target,'id':'other'};self.assertIsNone(m.dashboard(self.library,self.folder,'Introduction',other)['selected_plan'])

if __name__=='__main__':unittest.main()
