import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import preferences as p


class PreferenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=p.Store(Path(self.tmp.name)/'preferences')
        self.ctx={'workspace':'paper','section':'intro1','section_type':'introduction'}
        self.root=Path(self.tmp.name)/'library'
    def write(self, action='save', **kwargs):
        return self.store.mutate({'expected':self.store.snapshot()['version'],'action':action,**kwargs},self.ctx,self.root)
    def test_scope_and_exact_snapshot_history_restore(self):
        first=self.store.snapshot()['version']
        ids=[]
        for scope in p.SCOPES:
            self.write(item={'rule':scope+' rule','scope':scope,'sectionType':'introduction'},reason='create '+scope)
            ids.append(self.store.dashboard()['items'][-1]['id'])
        snap=self.store.snapshot(**self.ctx);self.assertEqual(len(snap['items']),4)
        self.assertEqual(len(self.store.snapshot('other','intro2','introduction')['items']),2)
        self.assertEqual(len(self.store.snapshot('paper','method','method')['items']),2)
        self.assertEqual(len(self.store.snapshot()['items']),1)
        version=snap['version'];item=snap['items'][0]
        self.write(id=item['id'],item={**item,'rule':'changed'},reason='revise')
        self.assertEqual(snap['items'][0]['rule'],'global rule')
        view=self.store.dashboard(revision=version);self.assertIn('changed',view['detail']['diff']);self.assertTrue(view['history'])
        self.write('restore',id=item['id'],revision=version,reason='restore single')
        self.assertEqual(self.store.snapshot()['items'][0]['rule'],'global rule')
        self.write('mark',reason='满意版本');self.assertEqual(self.store.dashboard()['history'][0]['action'],'mark')
        self.write('restore',revision=first,reason='restore all');self.assertEqual(self.store.snapshot()['items'],[])
        self.assertGreater(len(self.store.dashboard()['history']),7)
        with self.assertRaises(ValueError):self.store.at('--all')
    def test_conflict_and_commit_failure_are_non_destructive(self):
        self.write(item={'rule':'Preserve me'})
        head=self.store.snapshot()['version'];old=self.store.current()
        with self.assertRaises(ValueError):self.store.mutate({'action':'save','expected':'old','item':{'rule':'bad'}},self.ctx)
        original=self.store.git
        def fail(*args):
            if args[0]=='commit':raise ValueError('disk full')
            return original(*args)
        with patch.object(self.store,'git',side_effect=fail):
            with self.assertRaises(ValueError):self.write(item={'rule':'should roll back'})
        self.assertEqual(self.store.current(),old);self.assertEqual(self.store.snapshot()['version'],head)
    def test_learning_explicit_inferred_rejection_and_replacement(self):
        revision=self.store.snapshot()['version']
        prompt='以后避免 because。这个段落解释太长。'
        raw=[{'rule':'避免 because','scope':'global','quote':'以后避免 because。'}, {'rule':'本章节缩短解释','scope':'section','quote':'这个段落解释太长。'}, {'rule':'invented','quote':'not present'}]
        result=self.store.learn(raw,prompt,self.ctx,'run1',revision)
        self.assertEqual(result,{'active':1,'pending':1})
        rows=self.store.dashboard()['items'];pending=next(i for i in rows if i['status']=='pending');active=next(i for i in rows if i['status']=='active')
        self.write('reject',id=pending['id']);self.assertEqual(self.store.learn(raw,prompt,self.ctx,'run2',revision),{'active':0,'pending':0})
        rule={**active,'rule':'允许 because 的特定例外','quote':'以后允许 because 的特定例外。','targetId':active['id']}
        self.store.learn([rule],rule['quote'],self.ctx,'run3',self.store.snapshot()['version'])
        proposed=self.store.dashboard()['items'][-1];self.assertEqual(proposed['status'],'pending')
        self.write('accept',id=proposed['id']);self.assertEqual(self.store.snapshot()['items'][0]['rule'],rule['rule'])
    def test_stale_analysis_and_approval_do_not_overwrite_changes(self):
        old=self.store.snapshot()['version'];self.write(item={'rule':'new user edit'})
        self.store.learn([{'rule':'avoid because','quote':'以后避免 because。'}],'以后避免 because。',self.ctx,'r',old)
        self.assertEqual(self.store.dashboard()['items'][-1]['status'],'pending')
        active=self.store.snapshot()['items'][0]
        self.store.learn([{'rule':'replacement','quote':'以后替换规则。','targetId':active['id']}],'以后替换规则。',self.ctx,'r2',self.store.snapshot()['version'])
        proposal=self.store.dashboard()['items'][-1]
        self.write(item={**active,'rule':'newer'},id=active['id'])
        with self.assertRaises(ValueError):self.write('accept',id=proposal['id'])
    def test_author_evidence_and_pending_only(self):
        pid='a'*64;folder=self.root/pid;folder.mkdir(parents=True)
        (folder/'paper.json').write_text(json.dumps({'id':pid,'name':'XuefengDu_Test.pdf','chunks':[[{'id':'p1-b1','page':1,'text':'A concrete mechanism motivates the research question.'}]]}))
        raw={'rule':'先讲具体机制再引出问题','kind':'author_style','scope':'section_type','sectionType':'introduction','author':'xuefeng','quote':'以后参考 Du 这种写法。','evidence':[{'paperId':pid,'chunkId':'p1-b1','quote':'A concrete mechanism motivates the research question.'}]}
        self.assertEqual(self.store.learn([raw],raw['quote'],self.ctx,'r',self.store.snapshot()['version'],self.root),{'active':0,'pending':1})
        self.write('accept',id=self.store.dashboard()['items'][-1]['id']);self.assertEqual(len(self.store.snapshot(**self.ctx)['items']),1)
        raw['evidence'][0]['quote']='invented quote'
        with self.assertRaises(ValueError):self.store.validate(raw,**self.ctx,library_root=self.root)
    def test_background_analysis_success_failure_and_idempotency(self):
        from types import SimpleNamespace
        prompt='以后避免 because。'
        calls=[]
        def generate(body,timeout):
            calls.append(body)
            return {'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':json.dumps({'proposals':[{'rule':'Avoid because','quote':prompt,'scope':'global'}]})}]}}]}
        with patch.object(p.threading,'Thread',side_effect=lambda target,daemon:SimpleNamespace(start=target)):
            p.enqueue(self.store,self.ctx,prompt,'answer','previous','draft','learn',generate,self.root)
            self.assertEqual(p.job(self.store,'learn'),{'status':'done','active':1,'pending':0})
            p.enqueue(self.store,self.ctx,prompt,'answer','','','learn',generate,self.root)
            self.assertEqual(len(calls),1)
            before=self.store.snapshot()['version']
            p.enqueue(self.store,self.ctx,prompt,'','','','bad',lambda *a: (_ for _ in ()).throw(ValueError('model failed')),self.root)
            self.assertEqual(p.job(self.store,'bad')['status'],'failed')
            self.assertEqual(self.store.snapshot()['version'],before)
    def test_quoted_instructions_and_pending_edits_do_not_activate(self):
        raw={'rule':'Avoid because','quote':'以后避免 because。','scope':'global'}
        for prompt in ('```text\n以后避免 because。\n```','> 以后避免 because。'):
            self.assertEqual(self.store.learn([raw],prompt,self.ctx,'q',self.store.snapshot()['version']),{'active':0,'pending':0})
        self.store.learn([raw],'论文里的例句：“以后避免 because。”',self.ctx,'quoted',self.store.snapshot()['version'])
        pending=self.store.dashboard()['items'][-1];self.assertEqual(pending['status'],'pending')
        self.write('save',id=pending['id'],item={**pending,'rule':'Edited proposal'})
        self.assertEqual(self.store.snapshot()['items'],[])

    def test_disabled_learning_and_unrelated_chat(self):
        self.write('learning',enabled=False)
        result=p.enqueue(self.store,self.ctx,'以后不要 because','','','','run',lambda *a:self.fail('should not call'),self.root)
        self.assertEqual(result['status'],'skipped')
        self.assertFalse(p.signal('重新编译'))


if __name__=='__main__': unittest.main()
