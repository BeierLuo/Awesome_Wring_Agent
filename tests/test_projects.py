import copy,json,threading,unittest,urllib.request
import test_http as http_fixture
import server as s

class ProjectTests(unittest.TestCase):
    setUp=http_fixture.HTTPTests.setUp
    post=http_fixture.HTTPTests.post
    def action(self,action,revision=1,**extra):return self.post('/api/projects/'+action,{'id':'paper','revision':revision,**extra},{'X-Draft-Project':'1','Content-Type':'application/json'})
    def catalog(self,trash=False):
        with urllib.request.urlopen(f'http://127.0.0.1:{self.server.server_port}/api/projects'+('?trash=1' if trash else '')) as r:return json.load(r)['items']
    def test_catalog_rename_preserves_paper(self):
        folder=self.server.root/'paper';pdf=(folder/'original.pdf').read_bytes();config=s.read_config(self.server)
        self.assertEqual(self.catalog()[0]['type'],'PDF');self.assertEqual(self.catalog()[0]['sections'],1)
        code,result=self.action('rename',name='New Project');self.assertEqual(code,200)
        state=s.read_state(folder);self.assertEqual(state['name'],'New Project');self.assertEqual(state['revision'],2)
        self.assertEqual(state['sections'],self.state['sections']);self.assertEqual((folder/'original.pdf').read_bytes(),pdf);self.assertEqual(s.read_config(self.server),config)
        self.assertNotEqual(self.action('rename',name='Stale')[0],200)
    def test_recycle_restore_retains_all_files_and_blocks_stale_saves(self):
        folder=self.server.root/'paper';before={p.relative_to(folder):p.read_bytes() for p in folder.rglob('*') if p.is_file()}
        self.assertEqual(self.action('trash')[0],200);self.assertFalse(folder.exists());self.assertEqual(self.catalog(),[]);self.assertEqual(self.catalog(True)[0]['id'],'paper')
        self.assertEqual(self.post('/api/save',{'state':self.state})[0],409)
        self.assertEqual(self.action('restore')[0],200);self.assertEqual(self.catalog(True),[])
        for path,data in before.items():
            if str(path)!='workspace.json':self.assertEqual((folder/path).read_bytes(),data)
        self.assertEqual(s.read_state(folder)['revision'],2);self.assertEqual(self.post('/api/save',{'state':self.state})[0],409)
    def test_validation_header_origin_and_traversal(self):
        self.assertEqual(self.post('/api/projects/trash',{'id':'paper','revision':1})[0],403)
        for name in ['', '   ','x'*121,'Bad\nname']:
            self.assertEqual(self.action('rename',name=name)[0],400)
        code,_=self.post('/api/projects/trash',{'id':'../paper','revision':1},{'X-Draft-Project':'1'});self.assertEqual(code,400)
        code,_=self.post('/api/projects/trash',{'id':'paper','revision':1},{'X-Draft-Project':'1','Origin':'https://example.com'});self.assertEqual(code,403)
    def test_active_agent_and_compile_block_moves(self):
        s.RUNS['test-project-active']=threading.Event()
        try:self.assertEqual(self.action('trash')[0],409)
        finally:s.RUNS.pop('test-project-active')
        s.LATEX_BUILD_LOCK.acquire()
        try:self.assertEqual(self.action('trash')[0],409)
        finally:s.LATEX_BUILD_LOCK.release()
    def test_restore_collision_does_not_overwrite(self):
        self.assertEqual(self.action('trash')[0],200)
        s.write_state(self.server.root/'paper',self.state,None)
        self.assertEqual(self.action('restore')[0],400)
        self.assertEqual(len(self.catalog(True)),1)
    def test_symlink_project_cannot_be_moved(self):
        folder=self.server.root/'paper';outside=self.server.root.parent/'outside';folder.rename(outside);folder.symlink_to(outside,target_is_directory=True)
        self.assertEqual(self.action('trash')[0],400);self.assertTrue((outside/'workspace.json').exists())

if __name__=='__main__':unittest.main()
