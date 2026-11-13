import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import paragraph_selection as selection
from writing_agent import initial_contents


class SelectionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.folder=Path(self.temp.name).resolve()
        self.source='\\section{Method}\n\nFirst paragraph.\nStill first.\n\nSecond paragraph.\n\n\\begin{equation}\nx=1\n\ny=2\n\\end{equation}\n'
        file=self.folder/'latex/body.tex';file.parent.mkdir();file.write_text(self.source)
        mapping=self.folder/'.latex/builds/build/source-map.json';mapping.parent.mkdir(parents=True);mapping.write_text('{}')
        self.target={'id':'method','filename':'method.tex','title':'Method','initialized':True,'format':'latex','source_file':'body.tex','source_start':0,'source_end':len(self.source),'text':self.source,'versions':[{'id':'v1'}],'chat':[]}
        self.state={'sections':[self.target]}

    def resolve(self, lines):
        hits=[{'path':'body.tex','line':n} for n in lines]
        with patch('latex_project.inverse_search',return_value=hits[0]),patch('synctex_mapping.locate',side_effect=hits[1:]):
            return selection.resolve(self.folder,self.state,'build',[[i+1,20,30] for i in range(len(lines))])

    def test_paragraph_and_cross_page_selection(self):
        first=self.resolve([3,4]);self.assertEqual(first['text'],'First paragraph.\nStill first.\n')
        self.assertEqual(self.source[first['start']:first['end']],first['text'])
        second=self.resolve([6]);self.assertEqual(second['text'],'Second paragraph.\n')
        both=self.resolve([3,6]);self.assertEqual(both['text'],'First paragraph.\nStill first.\n\nSecond paragraph.\n')
        self.assertEqual(self.resolve([5])['text'],first['text'])
        self.assertEqual((first['startLine'],first['endLine']),(3,4))

    def test_environment_is_not_split_at_blank_lines(self):
        self.assertEqual(self.resolve([11])['text'],'\\begin{equation}\nx=1\n\ny=2\n\\end{equation}\n')

    def test_cross_file_and_section_rejected(self):
        with patch('latex_project.inverse_search',return_value={'path':'body.tex','line':3}),patch('synctex_mapping.locate',return_value={'path':'other.tex','line':3}):
            with self.assertRaisesRegex(ValueError,'多个 TeX'):selection.resolve(self.folder,self.state,'build',[[1,20,30],[2,20,30]])
        self.target['source_end']=self.source.index('Second')
        with self.assertRaisesRegex(ValueError,'跨越章节'):self.resolve([3,6])

    def test_validate_and_context_only_selected_source(self):
        result=self.resolve([6]);focus=selection.validate(self.target,result)
        self.target['selected_passage']=focus
        content=initial_contents(self.state,self.target,'polish')[-1]['parts'][0]['text']
        context=json.loads(content.split('最新 Project 状态（优先于历史旧稿）：\n',1)[1].split('\n\n本轮要求：',1)[0])['current_section']
        self.assertEqual(context['text'],focus['text'])
        self.assertNotIn('First paragraph.',context['text'])
        self.assertIn('First paragraph.',context['narrative_context']['before'])
        self.assertTrue(context['narrative_context']['read_only'])
        self.assertIn('selected_passage',content)
        for key,value in [('start',True),('end',-1),('version','old'),('text','invented')]:
            broken={**result,key:value}
            with self.assertRaises(ValueError):selection.validate(self.target,broken)
        self.target['text']='Changed'
        with self.assertRaises(ValueError):selection.validate(self.target,result)

    def test_narrative_context_is_bounded_and_selection_stays_exact(self):
        prefix='\\section{Method}\n'+'before '*1000
        selected='Interpretation and key insights.'
        suffix='after '*1000
        target={'title':'Method','text':prefix+selected+suffix,
                'selected_passage':{'start':len(prefix),'end':len(prefix)+len(selected),'text':selected}}
        context=selection.narrative_context(target)
        self.assertEqual(context['before'],prefix[-2400:])
        self.assertEqual(context['after'],suffix[:2400])
        self.assertTrue(context['before_truncated']);self.assertTrue(context['after_truncated'])
        self.assertEqual(context['preceding_headings'][0]['title'],'Method')
        self.assertEqual(target['selected_passage']['text'],selected)
        target['selected_passage']['start']=0
        self.assertEqual(selection.narrative_context(target)['status'],'unavailable')
        self.assertIsNone(selection.narrative_context({'text':'No selection'}))

    def test_invalid_points(self):
        for points in [[],None,[[1,2]],[[True,2,3]],[[1,'x',3]],[[1,2,3]]*257]:
            with self.assertRaises(ValueError):selection.resolve(self.folder,self.state,'build',points)

if __name__=='__main__':unittest.main()
