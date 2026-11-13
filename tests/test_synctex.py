import gzip
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import latex_project as latex
import synctex_mapping as sync

class SyncTests(unittest.TestCase):
    def test_coordinates_columns_and_project_boundary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);path=root/'main.synctex.gz'
            records='''SyncTeX Version:1
Input:1:./parts/body.tex
Input:2:/etc/secret.tex
Magnification:1000
Unit:65782
X Offset:0
Y Offset:0
Content:
{1
(1,9:50,100:150,10,2
g1,8:70,100
)
(1,21:300,103:150,10,2
g1,20:320,103
)
g2,1:72,100
}1
Postamble:
'''
            with gzip.open(path,'wt') as f:f.write(records)
            mapping=sync.read_mapping(path,root,{'parts/body.tex'})
            self.assertEqual(sync.locate(mapping,1,75,96)['line'],8)
            self.assertEqual(sync.locate(mapping,1,325,96)['line'],20)
            self.assertEqual(sync.locate(mapping,1,325,96)['path'],'parts/body.tex')
            for x in [float('nan'),float('inf'),-1]:
                with self.assertRaises(ValueError):sync.locate(mapping,1,x,0)
            with self.assertRaises(ValueError):sync.locate(mapping,2,75,96)

    def test_real_two_column_and_cross_page_passages(self):
        if not latex.compiler():self.skipTest('Tectonic is unavailable')
        import paragraph_selection
        import pymupdf
        with tempfile.TemporaryDirectory() as tmp:
            archive=io.BytesIO()
            first='Alphaunique '+('A paragraph with several words for wrapping. '*12)+'\n'
            second='Betaunique '+('Another paragraph with more words for wrapping. '*12)+'\n'
            third='Gammaunique Final page paragraph.\n'
            body='\\section{Method}\n\n'+first+'\n'+second+'\n\\clearpage\n\n'+third
            with zipfile.ZipFile(archive,'w') as z:
                z.writestr('main.tex','\\documentclass[twocolumn]{article}\n\\begin{document}\n\\input{body}\n\\end{document}\n')
                z.writestr('body.tex',body)
            folder,state=latex.import_project(Path(tmp).resolve(),archive.getvalue(),'columns.zip')
            result=latex.compile_project(folder,state)
            self.assertTrue(result['ok'],result['log'])
            with pymupdf.open(folder/'.latex/compiled.pdf') as doc:
                points=[]
                for word,expected in [('Alphaunique',first),('Betaunique',second),('Gammaunique',third)]:
                    found=[(i+1,r) for i,page in enumerate(doc) for r in page.search_for(word)]
                    self.assertEqual(len(found),1)
                    page,r=found[0];point=[page,(r.x0+r.x1)/2,(r.y0+r.y1)/2];points.append(point)
                    self.assertEqual(paragraph_selection.resolve(folder,state,result['runId'],[point])['text'],expected)
                merged=paragraph_selection.resolve(folder,state,result['runId'],points)
                self.assertIn(first,merged['text']);self.assertIn(third,merged['text'])
                self.assertGreater(points[-1][0],points[0][0])

    def test_real_compilation_and_version_guards(self):
        if not latex.compiler():self.skipTest('Tectonic is unavailable')
        with tempfile.TemporaryDirectory() as tmp:
            archive=io.BytesIO()
            with zipfile.ZipFile(archive,'w') as z:
                z.writestr('main.tex',r'''\documentclass{article}
\begin{document}
\input{parts/body}
\end{document}
''')
                z.writestr('parts/body.tex','First paragraph with several words.\n\nSecond paragraph with a formula $E=mc^2$.\n')
            folder,state=latex.import_project(Path(tmp).resolve(),archive.getvalue(),'sync.zip')
            result=latex.compile_project(folder,state)
            self.assertTrue(result['ok'],result['log'])
            import pymupdf
            with pymupdf.open(folder/'.latex/compiled.pdf') as doc:
                for word,line in [('First',1),('Second',3),('formula',3)]:
                    rect=doc[0].search_for(word)[0]
                    found=latex.inverse_search(folder,state,result['runId'],1,(rect.x0+rect.x1)/2,(rect.y0+rect.y1)/2)
                    self.assertEqual((found['path'],found['line']),('parts/body.tex',line))
                    import paragraph_selection
                    passage=paragraph_selection.resolve(folder,state,result['runId'],[[1,(rect.x0+rect.x1)/2,(rect.y0+rect.y1)/2]])
                    expected='First paragraph with several words.\n' if line==1 else 'Second paragraph with a formula $E=mc^2$.\n'
                    self.assertEqual(passage['text'],expected)
                    marks=paragraph_selection.highlight(folder,state,result['runId'],passage['sectionId'],passage['start'],passage['end'],passage['version'])
                    self.assertTrue(marks['rects'])
                    self.assertTrue(any(m[0]==1 and m[1]<=100*rect.x0/doc[0].rect.width<=m[1]+m[3] and m[2]<=100*rect.y0/doc[0].rect.height<=m[2]+m[4] for m in marks['rects']))


            import server, threading, urllib.request, urllib.parse
            server.write_state(folder,state,None)
            http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
            http.root=folder.parent
            thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
            try:
                query=urllib.parse.urlencode({'workspaceId':state['id'],'v':result['runId'],'page':1,'x':(rect.x0+rect.x1)/2,'y':(rect.y0+rect.y1)/2})
                with urllib.request.urlopen(f'http://127.0.0.1:{http.server_port}/api/latex/inverse-search?'+query) as response:
                    self.assertEqual(json.load(response)['path'],'parts/body.tex')
                with urllib.request.urlopen(f'http://127.0.0.1:{http.server_port}/api/latex/pdf-text?'+query) as response:
                    layer=json.load(response)
                    text='\n'.join(''.join(c[0] for c in line) for block in layer['blocks'] for line in block)
                    self.assertIn('First paragraph',text)
                    self.assertIn('Second paragraph',text)
                highlight_query=urllib.parse.urlencode({'workspaceId':state['id'],'v':result['runId'],'sectionId':passage['sectionId'],'start':passage['start'],'end':passage['end'],'version':passage['version']})
                with urllib.request.urlopen(f'http://127.0.0.1:{http.server_port}/api/latex/selection-highlight?'+highlight_query) as response:
                    self.assertTrue(json.load(response)['rects'])
                selection_query=urllib.parse.urlencode({'workspaceId':state['id'],'v':result['runId'],'points':json.dumps([[1,(rect.x0+rect.x1)/2,(rect.y0+rect.y1)/2]])})
                with urllib.request.urlopen(f'http://127.0.0.1:{http.server_port}/api/latex/selection?'+selection_query) as response:
                    self.assertEqual(json.load(response)['text'],'Second paragraph with a formula $E=mc^2$.\n')
                import urllib.error
                with self.assertRaises(urllib.error.HTTPError) as failure:
                    urllib.request.urlopen(f'http://127.0.0.1:{http.server_port}/api/latex/pdf-text?'+query.replace(result['runId'],'outdated'))
                self.assertEqual(failure.exception.code,400)
            finally:
                http.shutdown();http.server_close();thread.join()
            with self.assertRaises(ValueError):latex.inverse_search(folder,state,'old',1,100,100)
            (folder/'latex/parts/body.tex').write_text('Changed externally')
            with self.assertRaisesRegex(ValueError,'重新编译'):latex.inverse_search(folder,state,result['runId'],1,100,100)

if __name__=='__main__':unittest.main()
