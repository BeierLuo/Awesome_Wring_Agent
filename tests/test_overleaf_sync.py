import copy, json, os, subprocess, tempfile, unittest
from pathlib import Path
import overleaf_sync as o
import latex_project as l
from unittest.mock import patch

MAIN=b'\\documentclass{article}\n\\begin{document}\n\\section{Method}\nOriginal.\n\\end{document}\n'

class SyncTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve();self.remote=self.root/'remote';self.remote.mkdir()
        self.cmd('init','-b','master');self.cmd('config','user.name','Fixture');self.cmd('config','user.email','fixture@example.test')
        (self.remote/'main.tex').write_bytes(MAIN);(self.remote/'remote-only.bib').write_text('remote bib');(self.remote/'.gitignore').write_text('keep me');self.commit()
        self.folder=self.root/'paper';(self.folder/'latex').mkdir(parents=True);(self.folder/'.latex').mkdir()
        (self.folder/'latex/main.tex').write_bytes(MAIN)
        self.state={'id':'paper','revision':1,'sections':[],'selected':-1,'latex':{'main':'main.tex'}};l.refresh(self.folder,self.state,True)
        self.state['sections'][0]['chat']=[{'role':'user','text':'Keep this chat'}]
        remote=self.remote
        class LocalSync(o.Sync):
            def git(self,*args,**kwargs):
                return super().git('-c','protocol.file.allow=always',*[str(remote) if a.startswith('https://git@git.overleaf.com/') else a for a in args],**kwargs)
        # Git permits updating a checked-out branch only for this disposable test remote.
        self.cmd('config','receive.denyCurrentBranch','updateInstead')
        self.sync=LocalSync(self.root/'private','paper');self.sync.connect('https://www.overleaf.com/project/abcdef123','TEST_TOKEN')
    def cmd(self,*args):return subprocess.check_output(['git','-C',str(self.remote),*args],stderr=subprocess.DEVNULL).decode().strip()
    def commit(self):self.cmd('add','.');self.cmd('commit','-m','Fixture update')
    def apply(self,p,resolutions=None):
        def save(state):self.state=state
        return self.sync.apply(self.folder,self.state,p['previewId'],resolutions or {},save)
    def pull(self):return self.apply(self.sync.preview(self.folder,self.state,'pull'))
    def test_pull_push_preserves_chat_and_remote_unsupported_files(self):
        (self.folder/'latex/local-settings.json').write_text('PRIVATE_LOCAL_SETTING')
        initial=(self.folder/'latex/main.tex').read_bytes();p=self.sync.preview(self.folder,self.state,'pull')
        self.assertEqual((self.folder/'latex/main.tex').read_bytes(),initial);self.assertFalse((self.folder/'latex/remote-only.bib').exists())
        self.assertIn('.gitignore',p['skipped']);self.apply(p)
        self.assertEqual((self.folder/'latex/remote-only.bib').read_text(),'remote bib')
        (self.folder/'latex/main.tex').write_bytes(MAIN.replace(b'Original.',b'Local revision.'))
        p=self.sync.preview(self.folder,self.state,'push');self.apply(p)
        self.assertIn('Local revision.',(self.remote/'main.tex').read_text());self.assertEqual((self.remote/'.gitignore').read_text(),'keep me')
        self.assertEqual(self.state['sections'][0]['chat'][0]['text'],'Keep this chat')
        self.assertNotIn('connection.json',self.cmd('ls-tree','-r','--name-only','HEAD'))
        self.assertNotIn('local-settings.json',self.cmd('ls-tree','-r','--name-only','HEAD'))
        self.assertEqual((self.folder/'latex/local-settings.json').read_text(),'PRIVATE_LOCAL_SETTING')
        self.assertNotIn('TEST_TOKEN',json.dumps(self.sync.status()));self.assertNotIn('TEST_TOKEN',json.dumps(p))
        self.assertEqual(self.sync.config_path.stat().st_mode&0o777,0o600)
    def test_conflict_requires_explicit_choice_and_retains_local_only_edits(self):
        self.pull();(self.folder/'latex/main.tex').write_bytes(MAIN.replace(b'Original.',b'Local.'))
        (self.remote/'main.tex').write_bytes(MAIN.replace(b'Original.',b'Remote.'));self.commit()
        p=self.sync.preview(self.folder,self.state,'pull');self.assertEqual(p['changes'][0]['kind'],'conflict')
        with self.assertRaisesRegex(ValueError,'every conflict'):self.apply(p)
        self.apply(p,{'main.tex':'local'});self.assertIn(b'Local.',(self.folder/'latex/main.tex').read_bytes())
        p=self.sync.preview(self.folder,self.state,'push');self.assertEqual(p['changes'][0]['kind'],'local');self.apply(p)
        self.assertIn('Local.',(self.remote/'main.tex').read_text())
    def test_remote_and_local_changes_after_preview_are_rejected(self):
        self.pull();p=self.sync.preview(self.folder,self.state,'push')
        (self.remote/'remote-only.bib').write_text('new');self.commit()
        with self.assertRaisesRegex(ValueError,'Overleaf changed'):self.apply(p)
        p=self.sync.preview(self.folder,self.state,'pull');(self.folder/'latex/main.tex').write_bytes(MAIN+b'% external edit')
        with self.assertRaisesRegex(ValueError,'Local sources changed'):self.apply(p)
    def test_invalid_merge_does_not_change_either_side(self):
        self.pull();head=self.cmd('rev-parse','HEAD');(self.folder/'latex/main.tex').write_bytes(b'')
        p=self.sync.preview(self.folder,self.state,'push')
        with self.assertRaises(ValueError):self.apply(p)
        self.assertEqual(head,self.cmd('rev-parse','HEAD'))
    def test_deletion_and_new_files(self):
        self.pull();(self.remote/'remote-only.bib').unlink();(self.remote/'new.bib').write_text('new');self.commit()
        self.pull();self.assertFalse((self.folder/'latex/remote-only.bib').exists());self.assertEqual((self.folder/'latex/new.bib').read_text(),'new')
    def test_disconnect_invalidates_preview_and_clears_token(self):
        self.pull();self.sync.preview(self.folder,self.state,'push');self.sync.disconnect()
        self.assertFalse(self.sync.config_path.exists());self.assertFalse(self.sync.ticket_path.exists());self.assertFalse(self.sync.status()['connected'])
    def test_failed_save_rolls_back_local_sources(self):
        self.pull();old=l.files(self.folder);(self.remote/'main.tex').write_bytes(MAIN.replace(b'Original.',b'Remote.'));self.commit();p=self.sync.preview(self.folder,self.state,'pull')
        calls=[]
        def save(state):
            calls.append(state)
            if len(calls)==1:raise OSError('fixture save failure')
        with self.assertRaisesRegex(ValueError,'restored'):self.sync.apply(self.folder,self.state,p['previewId'],{},save)
        self.assertEqual(l.files(self.folder),old)
    def test_first_connection_does_not_assume_remote_is_ancestor(self):
        (self.folder/'latex/main.tex').write_bytes(MAIN.replace(b'Original.',b'Imported older draft.'))
        p=self.sync.preview(self.folder,self.state,'push');self.assertEqual(p['changes'][0]['kind'],'conflict')
    def test_git_errors_never_echo_credentials(self):
        with patch('overleaf_sync.subprocess.run',return_value=subprocess.CompletedProcess([],1,b'',b'password TEST_TOKEN')):
            with self.assertRaises(ValueError) as error:self.sync.git('fetch')
        self.assertNotIn('TEST_TOKEN',str(error.exception))
    def test_remote_change_during_push_is_not_overwritten(self):
        self.pull();(self.folder/'latex/main.tex').write_bytes(MAIN.replace(b'Original.',b'Local.'))
        p=self.sync.preview(self.folder,self.state,'push');git=self.sync.git
        def race(*args,**kwargs):
            if args[0]=='push':
                (self.remote/'main.tex').write_bytes(MAIN.replace(b'Original.',b'Collaborator edit.'));self.commit()
            return git(*args,**kwargs)
        with patch.object(self.sync,'git',side_effect=race):
            with self.assertRaises(ValueError):self.apply(p)
        self.assertIn('Collaborator edit.',(self.remote/'main.tex').read_text())
        self.assertIn('Local.',(self.folder/'latex/main.tex').read_text())

class ValidationTests(unittest.TestCase):
    def test_urls(self):
        self.assertEqual(o.normalize_url('git clone https://git@git.overleaf.com/abcdef'),'https://git@git.overleaf.com/abcdef')
        for url in ['https://evil.test/abcdef','https://git:secret@git.overleaf.com/abcdef','https://git.overleaf.com/abcdef?x=1','file:///tmp/repo','--upload-pack=x','http://git.overleaf.com/abcdef']:
            with self.assertRaises(ValueError):o.normalize_url(url)

if __name__=='__main__':unittest.main()
