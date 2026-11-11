import base64
import copy
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pymupdf
from writing_agent import WritingAgent, initial_contents, AgentStopped
from paper_tools import PaperTools


def final(text='Revised abstract.'):
    return {'candidates':[{'content':{'role':'model','parts':[{'text':text}]},'finishReason':'STOP'}],'usageMetadata':{'promptTokenCount':100,'totalTokenCount':120}}


def call(name,args,ident='call-1'):
    return {'candidates':[{'content':{'role':'model','parts':[{'functionCall':{'name':name,'args':args,'id':ident},'thoughtSignature':'opaque-test-signature'}]},'finishReason':'STOP'}]}


def research_call(name,args,ident='r1'):
    return {'status':'completed','output':[{'type':'function_call','call_id':ident,'name':name,'arguments':json.dumps(args)}]}


def evidence(ids=None,images=None):
    payload={'answer':'Verified result [q1-s1].','source_ids':ids or ['q1-s1'],'image_pages':images or [],'conflicts':[],'missing_information':[]}
    return {'status':'completed','output':[{'type':'message','role':'assistant','content':[{'type':'output_text','text':json.dumps(payload)}]}],'usage':{'input_tokens':50,'output_tokens':20}}


class AgentTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.folder=Path(self.temp.name)
        self.sections=[{'id':'abstract','filename':'01-abstract.md','title':'Abstract','text':'CURRENT_ABSTRACT: We introduce a method.','initialized':True,'start_page':1,'end_page':1,'versions':[{'id':'v1'}],'chat':[]}, {'id':'experiment','filename':'02-experiments.md','title':'Experiments','text':'LATEST_EXPERIMENT: accuracy is 93.4 percent.','initialized':True,'start_page':2,'end_page':3,'versions':[{'id':'v2'}],'chat':[]}]
        self.state={'id':'paper','sections':self.sections,'general':{'chat':[]}}
        doc=pymupdf.open()
        for i in range(1,5):
            page=doc.new_page();page.insert_text((70,70),f'{i} Section {i}\nORIGINAL_PAGE_{i}: baseline accuracy is 80 percent.\n'+('Source explanation. '*8))
        doc.save(self.folder/'original.pdf');doc.close()
        self.original=(self.folder/'original.pdf').read_bytes()

    def run_agent(self,responses,run='run-1',target=0,research=None):
        requests=[]
        def generate(body,timeout):
            requests.append(copy.deepcopy(body));return responses[len(requests)-1]
        self.research_requests=[]
        def assistant(body,timeout):
            self.research_requests.append(copy.deepcopy(body));return research[len(self.research_requests)-1]
        agent=WritingAgent(self.folder,self.state,self.sections[target] if target is not None else None,'polish',generate,run,assistant_generate=assistant if research is not None else None)
        result=agent.run()
        self.assertEqual((self.folder/'original.pdf').read_bytes(),self.original)
        return result,requests

    def test_polish_is_current_section_only_no_pdf_io(self):
        with patch.object(PaperTools,'index',side_effect=AssertionError('PDF should not be read')):
            result,requests=self.run_agent([final()])
        request=json.dumps(requests[0])
        self.assertIn('CURRENT_ABSTRACT',request)
        for unwanted in ['LATEST_EXPERIMENT','ORIGINAL_PAGE','inlineData','fileData','application/pdf']:
            self.assertNotIn(unwanted,request)
        self.assertEqual(result['trace'],[]);self.assertEqual(result['context']['pdfPages'],[])
        self.assertEqual(result['usage']['promptTokenCount'],100)
        self.assertTrue((self.folder/'.agent/runs/run-1/checkpoints.sqlite').exists())
        self.assertFalse((self.folder/'.agent/pdf-index.json').exists())

    def test_latex_writing_needs_neither_pdf_nor_gpt(self):
        self.sections[0].update(format='latex',filename='01-abstract.tex',source_file='sections/abstract.tex',text=r'\begin{abstract}Current $x=1$.\end{abstract}')
        self.state['latex']={'main':'main.tex'}
        with patch.object(PaperTools,'index',side_effect=AssertionError('PDF should not be read')):
            result,requests=self.run_agent([final('```latex\n'+self.sections[0]['text']+'\n```')])
        payload=json.dumps(requests[0],ensure_ascii=False)
        self.assertIn('sections/abstract.tex',payload)
        self.assertIn('只替换当前源码块',payload)
        self.assertNotIn('LATEST_EXPERIMENT',payload)
        self.assertEqual(result['assistantCalls'],0)
        self.assertEqual(result['baseVersion'],'v1')

    def test_reads_latest_other_section_only_when_called(self):
        result,requests=self.run_agent([call('ask_paper_assistant',{'question':'Verify the latest accuracy'}),final()],research=[research_call('read_section',{'section_id':'experiment'}),evidence()])
        self.assertEqual([t['name'] for t in requests[0]['tools'][0]['functionDeclarations']],['ask_paper_assistant','find_style_examples','read_style_memory','recommend_writing_strategy'])
        self.assertNotIn('LATEST_EXPERIMENT',json.dumps(requests[0]))
        self.assertNotIn('LATEST_EXPERIMENT',json.dumps(self.research_requests[0]))
        self.assertIn('LATEST_EXPERIMENT',json.dumps(requests[1]))
        self.assertNotIn('ORIGINAL_PAGE',json.dumps(requests))
        self.assertEqual(requests[1]['contents'][-2]['parts'][0]['thoughtSignature'],'opaque-test-signature')
        self.assertEqual(requests[1]['contents'][-1]['parts'][0]['functionResponse']['id'],'call-1')
        self.assertEqual(result['evidence'][0]['sources'][0]['version'],1)
        self.assertEqual(result['assistantUsage']['input_tokens'],50)
        self.assertEqual(result['assistantCalls'],2)

    def test_search_then_targeted_pdf_page_and_image(self):
        result,requests=self.run_agent([call('ask_paper_assistant',{'question':'Check page two figure','need_images':True}),final()],research=[research_call('search_paper',{'query':'ORIGINAL_PAGE_2','source':'pdf'}),research_call('read_pdf_pages',{'start_page':2,'mode':'image'}),evidence(ids=['q1-s2'],images=[2])])
        self.assertNotIn('ORIGINAL_PAGE',json.dumps(requests[0]))
        parts=requests[1]['contents'][-1]['parts']
        images=[image['inlineData'] for p in parts for image in p.get('functionResponse',{}).get('parts',[])]
        self.assertEqual(len(images),1);self.assertEqual(images[0]['mimeType'],'image/png')
        self.assertTrue(base64.b64decode(images[0]['data']).startswith(b'\x89PNG'))
        research_inputs=self.research_requests[-1]['input'][-1]['output']
        actual_payload=json.loads(research_inputs[0]['text'])
        self.assertEqual(actual_payload['output']['pages'][0]['source_id'],'q1-s2')
        self.assertEqual(next(p['image_url'] for p in research_inputs if p['type']=='input_image'),'data:image/png;base64,'+images[0]['data'])
        self.assertEqual(result['context']['pdfPages'],[2]);self.assertEqual(result['context']['imagePages'],[2])
        self.assertNotIn('fileData',json.dumps(requests))
        for path in (self.folder/'.agent/runs/run-1').glob('*.sqlite'):
            connection=sqlite3.connect(path);dump=''.join(connection.iterdump());connection.close()
            self.assertNotIn(images[0]['data'][:100],dump)
        paper=PaperTools(self.folder,self.state)
        with patch('paper_tools.pymupdf.open',side_effect=AssertionError('index should be reused')):
            self.assertEqual(len(paper.index()['pages']),4)

    def test_writer_cannot_bypass_helper(self):
        with patch.object(PaperTools,'execute',side_effect=AssertionError('Writer may not read')):
            result,requests=self.run_agent([call('read_section',{'section_id':'experiment'}),final()])
        self.assertNotIn('LATEST_EXPERIMENT',json.dumps(requests))
        self.assertEqual(result['trace'][0]['status'],'limited')

    def test_unverified_sources_and_images_blocked(self):
        for n,payload in enumerate([evidence(ids=['invented']),evidence(images=[3])]):
            result,requests=self.run_agent([call('ask_paper_assistant',{'question':'Verify'}),final()],run=f'invalid-{n}',research=[research_call('read_section',{'section_id':'experiment'}),payload])
            response=requests[-1]['contents'][-1]['parts'][0]['functionResponse']['response']
            self.assertIn('error',response);self.assertEqual(result['evidence'],[])
            self.assertNotIn('inlineData',json.dumps(requests))

    def test_helper_failure_is_explicit_and_no_extra_reads(self):
        result,requests=self.run_agent([call('ask_paper_assistant',{'question':'Verify'}),final()])
        self.assertIn('error',requests[-1]['contents'][-1]['parts'][0]['functionResponse']['response'])
        self.assertEqual(result['context']['pdfPages'],[])

    def test_followup_consultation_keeps_separate_evidence(self):
        result,requests=self.run_agent([call('ask_paper_assistant',{'question':'Verify experiment'}),call('ask_paper_assistant',{'question':'Check original page','need_images':True}),final()],research=[research_call('read_section',{'section_id':'experiment'}),evidence(),research_call('read_pdf_pages',{'start_page':2,'mode':'image'}),evidence(ids=['q2-s1'],images=[2])])
        self.assertEqual(result['assistantCalls'],4)
        self.assertEqual(len(result['evidence']),2)
        self.assertEqual(result['evidence'][1]['sources'][0]['source_id'],'q2-s1')
        self.assertNotIn('LATEST_EXPERIMENT',json.dumps(self.research_requests[2]))
        self.assertIn('LATEST_EXPERIMENT',json.dumps(requests[-1]))

    def test_cancellation_during_helper_stops_writer(self):
        event=threading.Event();writer_calls=[]
        def writer(body,timeout):
            writer_calls.append(body);return call('ask_paper_assistant',{'question':'Verify'})
        def helper(body,timeout):
            event.set();return evidence()
        with self.assertRaises(AgentStopped):
            WritingAgent(self.folder,self.state,self.sections[0],'hi',writer,'stop-helper',cancel=event,assistant_generate=helper).run()
        self.assertEqual(len(writer_calls),1)

    def test_tool_results_are_not_replayed_next_turn(self):
        self.sections[0]['chat']=[{'role':'user','text':'Earlier request'},{'role':'model','text':'Short earlier answer','content':{'parts':[{'inlineData':{'data':'HUGE_OLD_PDF'}},{'functionResponse':{'response':{'text':'OLD_TOOL_CONTEXT'}}}]},'agent':{'trace':[{'text':'OLD_TOOL_CONTEXT'}]}}]
        result,requests=self.run_agent([final()])
        self.assertNotIn('HUGE_OLD_PDF',json.dumps(requests));self.assertNotIn('OLD_TOOL_CONTEXT',json.dumps(requests))
        self.sections[0]['text']='NEWEST_CURRENT_VERSION'
        result,requests=self.run_agent([final()],run='run-2')
        self.assertIn('NEWEST_CURRENT_VERSION',json.dumps(requests[0]))
        self.assertNotIn('CURRENT_ABSTRACT',json.dumps(requests[0]))

    def test_bad_tool_and_scope_bounds(self):
        paper=PaperTools(self.folder,self.state)
        for name,args in [('write_file',{'path':'../secret'}),('read_section',{'section_id':'../secret'}),('read_pdf_pages',{'start_page':0}),('read_pdf_pages',{'start_page':1,'end_page':4}),('read_section',{'section_id':'abstract','max_chars':999999})]:
            with self.assertRaises(ValueError):paper.execute(name,args)
        result,requests=self.run_agent([call('write_file',{'path':'../secret'}),final()])
        self.assertEqual(result['trace'][0]['status'],'limited');self.assertIn('error',requests[1]['contents'][-1]['parts'][0]['functionResponse']['response'])

    def test_unlimited_tool_rounds_and_cancel(self):
        result,requests=self.run_agent([call('ask_paper_assistant',{'question':'Verify'})]*12+[final()])
        self.assertEqual(len(requests),13)
        self.assertEqual(requests[-1]['toolConfig']['functionCallingConfig']['mode'],'AUTO')
        self.assertEqual(result['finishReason'],'STOP')
        research=[research_call('list_sections',{})]*10+[evidence(ids=[])]
        result,_=self.run_agent([call('ask_paper_assistant',{'question':'Verify'})]+[final()],run='long-research',research=research)
        self.assertEqual(len(self.research_requests),11)
        self.assertTrue(all(r['tool_choice']=='auto' for r in self.research_requests))
        event=threading.Event();event.set()
        with self.assertRaises(AgentStopped):
            WritingAgent(self.folder,self.state,self.sections[0],'hi',lambda *args:self.fail('cancelled model must not be called'),'cancel',cancel=event).run()

    def test_history_budget_and_uninitialized(self):
        self.sections[0]['chat']=[{'role':'user' if i%2==0 else 'model','text':'x'*10000} for i in range(20)]
        history=initial_contents(self.state,self.sections[0],'new')
        self.assertLess(len(json.dumps(history)),12000)
        self.sections[1]['initialized']=False
        result=PaperTools(self.folder,self.state).read_section('experiment')
        self.assertFalse(result['initialized']);self.assertNotIn('LATEST_EXPERIMENT',str(result))

if __name__=='__main__':unittest.main()
