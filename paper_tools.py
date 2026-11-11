"""Bounded, read-only paper tools. PDF extraction and indexing stay on this machine."""
import base64
import hashlib
import json
import re
import threading
import uuid
from pathlib import Path
import pymupdf

INDEX_LOCK = threading.Lock()
MAX_PAGE_TEXT = 100000
MAX_PAGES = 500


def private_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        tmp.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
        tmp.chmod(0o600)
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)


def bounded_int(value, low, high, label):
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ValueError(f'{label} 必须为 {low}–{high} 的整数')
    return value


class PaperTools:
    def __init__(self, folder, workspace):
        self.folder = Path(folder).resolve()
        self.workspace = workspace  # Immutable snapshot of latest reconciled files for this run.
        self.sections = workspace.get('sections', [])
        self.pdf = self.folder / ('.latex/compiled.pdf' if workspace.get('latex') else 'original.pdf')
        self.pdf_source='compiled_pdf' if workspace.get('latex') else 'original_pdf'
        self.pdf_stale=False
        if workspace.get('latex'):
            metadata=self.folder/'.latex/pdf-build.json'
            built=json.loads(metadata.read_text()) if metadata.exists() else {}
            self.pdf_stale=built.get('sourceHash')!=workspace['latex'].get('sourceHash')
        self._index = None
        self.tool_chars = 0
        self.pdf_pages = set()
        self.image_pages = set()

    def index(self):
        if self.pdf_stale:raise ValueError('LaTeX 源码尚未编译或已更新；请先编译最新 PDF。可先读取最新章节源码。')
        if self._index is not None:
            return self._index
        if not self.pdf.is_file() or self.pdf.is_symlink():
            raise ValueError('当前工作区没有可读取的原始 PDF')
        raw = self.pdf.read_bytes()
        if len(raw) > (25 if self.workspace.get('latex') else 12) * 1024 * 1024:
            raise ValueError('PDF 超过本地读取大小限制')
        digest = hashlib.sha256(raw).hexdigest()
        cache = self.folder / '.agent' / 'pdf-index.json'
        with INDEX_LOCK:
            if cache.exists():
                try:
                    data = json.loads(cache.read_text())
                    if data.get('sha256') == digest and data.get('format') == 1:
                        self._index = data
                        return data
                except (ValueError, OSError):
                    pass
            pages = []
            try:
                with pymupdf.open(stream=raw, filetype='pdf') as doc:
                    if doc.needs_pass:
                        raise ValueError('PDF 已加密，请先提供可读取的文件')
                    if not 1 <= len(doc) <= MAX_PAGES:
                        raise ValueError('本地索引支持 1–500 页 PDF')
                    toc = doc.get_toc()[:500]
                    for i, page in enumerate(doc):
                        text = page.get_text('text', sort=True)
                        spans = [span for block in page.get_text('dict')['blocks'] if 'lines' in block for line in block['lines'] for span in line['spans']]
                        sizes = sorted(s['size'] for s in spans if s['text'].strip())
                        body_size = sizes[len(sizes)//2] if sizes else 10
                        headings = []
                        for line in text.splitlines():
                            line = line.strip()
                            if re.match(r'^(?:\d+(?:\.\d+)*\.?\s+\S|abstract\b|introduction\b|conclusion\b|references\b|appendix\b|摘要|引言|结论)', line, re.I) and len(line) <= 140:
                                headings.append(line)
                        headings += [s['text'].strip() for s in spans if s['size'] >= body_size+1 and 2 < len(s['text'].strip()) < 140]
                        pages.append({'page': i+1, 'text': text[:MAX_PAGE_TEXT], 'truncated': len(text)>MAX_PAGE_TEXT, 'needs_image': len(text.strip())<60, 'headings': list(dict.fromkeys(headings))[:18]})
            except ValueError:
                raise
            except Exception:
                raise ValueError('PDF 本地解析失败，请检查文件是否损坏或加密') from None
            data = {'format': 1, 'sha256': digest, 'pages': pages, 'toc': toc}
            private_json(cache, data)
            self._index = data
            return data

    def list_sections(self, offset=0):
        offset = bounded_int(offset, 0, 300, '目录偏移')
        items = [{'id': s['id'], 'title': s['title'], 'file': s['filename'], 'initialized': bool(s.get('initialized')), 'version': len(s.get('versions', [])), 'start_page': s.get('start_page'), 'end_page': s.get('end_page')} for s in self.sections[offset:offset+100]]
        return {'sections': items, 'next_offset': offset+100 if offset+100<len(self.sections) else None}

    def read_section(self, section_id, offset=0, max_chars=12000):
        section = next((s for s in self.sections if s['id']==section_id or s['filename']==section_id), None)
        if section is None:
            raise ValueError('章节不存在，请使用 list_sections 返回的 id 或文件名')
        if not section.get('initialized'):
            return {'id': section['id'], 'initialized': False, 'message': '该章节还没有当前稿，可读取原始 PDF 页，但不能将原始内容称为最新稿。', 'start_page': section.get('start_page'), 'end_page': section.get('end_page')}
        text = section['text']
        offset = bounded_int(offset, 0, len(text), '文字偏移')
        max_chars = bounded_int(max_chars, 1, 12000, '读取长度')
        end = min(offset+max_chars, len(text))
        return {'id': section['id'], 'file': section['filename'], 'version': len(section.get('versions', [])), 'source': 'latest_section', 'text': text[offset:end], 'offset': offset, 'next_offset': end if end<len(text) else None}

    def search_paper(self, query, source='all', max_results=5):
        if not isinstance(query, str) or not 1 <= len(query.strip()) <= 200:
            raise ValueError('搜索词长度应为 1–200 字符')
        if source not in {'all', 'sections', 'pdf'}:
            raise ValueError('搜索范围应为 all、sections 或 pdf')
        max_results = bounded_int(max_results, 1, 8, '结果数量')
        terms = list(dict.fromkeys([query.casefold().strip()] + re.findall(r'[\w-]{2,}', query.casefold())))[:12]
        docs = []
        if source in {'all', 'sections'}:
            docs += [({'source':'latest_section', 'id':s['id'], 'file':s['filename'], 'version':len(s.get('versions', []))}, s['text']) for s in self.sections if s.get('initialized')]
        if source=='pdf' and self.pdf_stale:raise ValueError('请先编译最新 PDF；源码已更新。')
        if source in {'all', 'pdf'} and self.pdf.exists() and not self.pdf_stale:
            docs += [({'source':self.pdf_source, 'page':p['page']},p['text']) for p in self.index()['pages']]
        hits = []
        for meta, text in docs:
            lower = text.casefold()
            matches = [(lower.find(t), t) for t in terms if t in lower]
            if not matches:
                continue
            pos = min(p for p,t in matches)
            start = max(0,pos-180)
            hits.append((len(matches), meta.get('source')=='latest_section', {**meta,'offset':start,'excerpt':text[start:start+700]}))
        hits.sort(key=lambda x:(x[1],x[0]),reverse=True)
        index = self._index
        return {'query': query, 'matches': [h[2] for h in hits[:max_results]], 'notice':('最新章节优先；PDF 来源：'+self.pdf_source+'。'+('源码已更新，暂未搜索旧 PDF。' if self.pdf_stale else '')+'关键词搜索可能漏检。'), 'scanned_pages': [p['page'] for p in index['pages'] if p['needs_image']][:20] if index else []}

    def read_pdf_pages(self, start_page, end_page=None, mode='text', offset=0):
        pages = self.index()['pages']
        start = bounded_int(start_page, 1, len(pages), '起始页')
        end = bounded_int(end_page if end_page is not None else start, start, min(start+1,len(pages)), '结束页')
        if mode not in {'text', 'image'}:
            raise ValueError('读取方式应为 text 或 image')
        selected = set(range(start,end+1))
        if len(self.pdf_pages | selected)>6:
            raise ValueError('本轮 PDF 阅读已达到 6 页上限，请缩小任务或下一轮继续')
        if mode=='image' and len(self.image_pages | selected)>2:
            raise ValueError('本轮页面图像已达到 2 页上限')
        offset = bounded_int(offset, 0, MAX_PAGE_TEXT, '页内偏移')
        result = []
        for p in pages[start-1:end]:
            text = p['text']
            if offset>len(text):
                raise ValueError('页内偏移超出正文长度')
            stop = min(offset+5000,len(text))
            result.append({'page':p['page'], 'text':text[offset:stop], 'offset':offset, 'next_offset':stop if stop<len(text) else None, 'needs_image':p['needs_image'], 'extraction_truncated':p['truncated']})
        self.pdf_pages |= selected
        if mode=='image':
            self.image_pages |= selected
        return {'source':self.pdf_source,'pages':result,'notice':'PDF 来源：'+self.pdf_source+'。文字提取可能丢失双栏顺序、公式或图表；有疑问时用 image 查看指定页面。', 'image_pages': sorted(selected) if mode=='image' else []}

    def image(self, page_number):
        count = len(self.index()['pages'])
        bounded_int(page_number,1,count,'页码')
        with pymupdf.open(self.pdf) as doc:
            page=doc[page_number-1]
            scale=min(2,1800/max(page.rect.width,page.rect.height))
            pix=page.get_pixmap(matrix=pymupdf.Matrix(scale,scale),alpha=False)
            data=pix.tobytes('png')
        if len(data)>4*1024*1024:
            raise ValueError('页面图像过大，请先压缩原始 PDF')
        return {'mimeType':'image/png','data':base64.b64encode(data).decode()}

    def outline(self):
        index=self.index()
        pages=[{'page':p['page'],'headings':p['headings'],'opening':p['text'][:180],'needs_image':p['needs_image']} for p in index['pages']]
        # Keep every page number; shorten candidates rather than silently dropping later pages.
        while len(json.dumps(pages,ensure_ascii=False))>40000:
            changed=False
            for p in pages:
                if p['opening']:p['opening']='';changed=True
                elif len(p['headings'])>1:p['headings']=p['headings'][:max(1,len(p['headings'])//2)];changed=True
                elif p['headings'] and len(p['headings'][0])>40:p['headings']=[p['headings'][0][:40]];changed=True
            if not changed:break
        return {'page_count':len(pages),'bookmarks':index['toc'][:100],'page_candidates':pages,'notice':'本地提取的标题候选，可能包含页眉和普通文字；章节边界需要核对。'}

    def execute(self, name, args):
        if name not in {'list_sections','read_section','search_paper','read_pdf_pages'} or not isinstance(args,dict):
            raise ValueError('未知工具或参数无效')
        if self.tool_chars>=48000:
            raise ValueError('本轮资料读取已达长度上限，请根据已有资料回答或下一轮继续')
        try:
            result=getattr(self,name)(**args)
        except TypeError:
            raise ValueError('工具参数不正确，请按声明使用') from None
        size=len(json.dumps(result,ensure_ascii=False))
        if self.tool_chars+size>48000:
            raise ValueError('本轮资料读取将超过长度上限，请缩小读取范围')
        self.tool_chars+=size
        return result
