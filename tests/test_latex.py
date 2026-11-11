import copy,io,json,stat,sys,tempfile,unittest,zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import latex_project as l
from paper_tools import PaperTools

def archive(files):
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w') as z:
        for name,data in files.items():z.writestr(name,data)
    return out.getvalue()

FIXTURE={'project/main.tex':r'''\documentclass{article}
% Keep this preamble exactly.
\begin{document}
\begin{abstract}Original abstract $E=mc^2$.\end{abstract}
\input{sections/body}
\bibliography{references}
\end{document}
''','project/sections/body.tex':r'''\section{Introduction}
First paragraph with \cite{paper}.
\section{Method}
\label{sec:method}
\begin{equation}x=1\end{equation}
''','project/references.bib':'@article{paper,title={Paper}}','project/figure.pdf':b'%PDF-fixture'}

class LatexTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve();self.folder,self.state=l.import_project(self.root,archive(FIXTURE),'paper.zip')
    def test_import_all_sections_assets_and_export(self):
        self.assertEqual([s['title'] for s in self.state['sections']],['Abstract','Introduction','Method'])
        self.assertTrue(all(s['initialized'] and s['text'] for s in self.state['sections']))
        with zipfile.ZipFile(io.BytesIO(l.export_zip(self.folder))) as z:
            self.assertEqual(set(z.namelist()),{n.removeprefix('project/') for n in FIXTURE})
            for n,v in FIXTURE.items():self.assertEqual(z.read(n.removeprefix('project/')),v.encode() if isinstance(v,str) else v)
    def test_section_adoption_updates_only_exact_span_and_preserves_chat(self):
        state=copy.deepcopy(self.state);s=state['sections'][1];s['text']=s['text'].replace('First paragraph','Revised paragraph');s['chat']=[{'role':'user','text':'revise'}]
        original=(self.folder/'latex/sections/body.tex').read_text();main=(self.folder/'latex/main.tex').read_bytes()
        l.apply_sections(self.folder,self.state,state)
        self.assertEqual((self.folder/'latex/sections/body.tex').read_text(),original.replace('First paragraph','Revised paragraph'))
        self.assertEqual((self.folder/'latex/main.tex').read_bytes(),main)
        self.assertEqual(state['sections'][1]['chat'],s['chat']);self.assertNotEqual(state['latex']['sourceHash'],self.state['latex']['sourceHash'])
        self.assertEqual(state['sections'][2]['source_start'],state['sections'][1]['source_end'])
    def test_external_structure_change_matches_title_not_position(self):
        state=self.state;method=state['sections'][2];method['chat']=[{'text':'method chat'}]
        p=self.folder/'latex/sections/body.tex';p.write_text('\\section{New}\nNew text\n'+p.read_text())
        self.assertTrue(l.refresh(self.folder,state))
        current=next(s for s in state['sections'] if s['title']=='Method')
        self.assertEqual(current['id'],method['id']);self.assertEqual(current['chat'],method['chat'])
        self.assertEqual(next(s for s in state['sections'] if s['title']=='New')['chat'],[])

    def test_include_order_paths_cycles_and_exact_writeback(self):
        sources={'main.tex':r'''\documentclass{article}
\begin{document}
\begin{abstract}Original abstract.\end{abstract}
\input{./parts/intro}
\section{Method}Method $x=1$.
\include{parts/experiment}
\section{Conclusion}Conclusion.
\end{document}''',
            'parts/intro.tex':r'\section{Introduction}Intro.\input details',
            'parts/details.tex':r'\section{Background}Background.\input{../main}',
            'parts/experiment.tex':r'\section{Experiments}Results \cite{key}.',
            'unused.tex':r'\section{Unused}Not in main.'}
        folder,state=l.import_project(self.root,archive(sources),'ordered.zip')
        self.assertEqual([s['title'] for s in state['sections']],['Abstract','Introduction','Background','Method','Experiments','Conclusion'])
        self.assertTrue(all(s['initialized'] for s in state['sections']))
        edited=copy.deepcopy(state)
        for section in edited['sections']:
            section['text']=section['text'].replace('Method $x=1$.','Method $x=2$.').replace('Results', 'New results')
        l.apply_sections(folder,state,edited)
        for name,text in sources.items():
            expected=text.replace('Method $x=1$.','Method $x=2$.').replace('Results','New results')
            self.assertEqual((folder/'latex'/name).read_text(),expected)
        self.assertEqual([s['id'] for s in edited['sections']],[s['id'] for s in state['sections']])

    def test_parser_upgrade_preserves_user_state(self):
        section=self.state['sections'][1];section['chat']=[{'text':'preserve chat'}]
        self.state['selected']=1;self.state['latex'].pop('parserVersion')
        self.assertTrue(l.refresh(self.folder,self.state))
        self.assertEqual(self.state['sections'][1]['id'],section['id'])
        self.assertEqual(self.state['sections'][1]['chat'],section['chat'])
        self.assertEqual(self.state['selected'],1)
        self.assertFalse(l.refresh(self.folder,self.state))
    def test_file_edit_conflict_and_rollback(self):
        p=self.folder/'latex/main.tex';raw=p.read_bytes()
        with self.assertRaises(ValueError):l.edit_file(self.folder,self.state,'main.tex','bad','wronghash')
        self.assertEqual(p.read_bytes(),raw)
        with self.assertRaises(ValueError):l.edit_file(self.folder,self.state,'main.tex','',l.digest(raw))
        self.assertEqual(p.read_bytes(),raw)
    def test_zip_traversal_links_duplicates_limits_and_encoding(self):
        for files in [{'../escape.tex':'x'},{'/absolute.tex':'x'},{'bad\\name.tex':'x'},{'Main.tex':'x','main.tex':'y'},{'main.tex':b'\xff'}]:
            with self.assertRaises(ValueError):l.unzip(archive(files))
        out=io.BytesIO()
        with zipfile.ZipFile(out,'w') as z:
            item=zipfile.ZipInfo('main.tex');item.external_attr=(stat.S_IFLNK|0o777)<<16;z.writestr(item,'/etc/passwd')
        with self.assertRaises(ValueError):l.unzip(out.getvalue())
        with self.assertRaises(ValueError):l.unzip(b'not a zip')
    def test_comment_verbatim_and_balanced_heading(self):
        text=r'''% \section{Fake}
\begin{verbatim}\section{Fake too}\end{verbatim}
\section{A \textbf{nested} title}
Body
\subsection{Child} Child content'''
        parts=l.blocks(text,'part.tex');self.assertEqual(len(parts),1);self.assertIn('nested',parts[0][2]);self.assertIn('subsection',text[parts[0][0]:parts[0][1]])
    def test_main_selection_invalidates_compiled_pdf(self):
        state=self.state;l.write(self.folder/'latex/alternate.tex',r'\documentclass{article}\begin{document}Alternate\end{document}');l.refresh(self.folder,state)
        before=state['latex']['sourceHash'];state['latex']['main']='alternate.tex';l.refresh(self.folder,state,True)
        self.assertNotEqual(before,state['latex']['sourceHash'])
    def test_uncompiled_and_stale_pdf_use_latest_sources(self):
        tools=PaperTools(self.folder,self.state)
        self.assertTrue(tools.search_paper('Original')['matches'])
        with self.assertRaisesRegex(ValueError,'编译'):tools.read_pdf_pages(1)
        l.write(self.folder/'.latex/compiled.pdf',b'%PDF-old')
        self.assertTrue(tools.search_paper('Original')['matches'])
        with self.assertRaisesRegex(ValueError,'编译'):tools.search_paper('Original',source='pdf')
    def test_outside_symlink_rejected(self):
        (self.folder/'latex/leak.tex').symlink_to(self.root/'secret')
        with self.assertRaises(ValueError):l.files(self.folder)

if __name__=='__main__':unittest.main()
