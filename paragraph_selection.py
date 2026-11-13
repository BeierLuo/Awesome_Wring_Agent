"""Resolve PDF selections into exact, versioned source spans without an LLM."""
import json
import re


def narrative_context(target, limit=2400):
    """Bounded, read-only surroundings; never widen the editable selection."""
    focus = target.get('selected_passage')
    if not focus:
        return None
    text = target.get('text', '')
    a, b = focus.get('start'), focus.get('end')
    if (type(a) is not int or type(b) is not int or
        not 0 <= a < b <= len(text) or text[a:b] != focus.get('text')):
        return {'status':'unavailable', 'notice':'选区与章节不一致，不能推断上下文或叙事位置。'}
    headings = []
    for match in re.finditer(r'(?m)^[ \t]*\\(section|subsection|subsubsection|paragraph)\*?\{([^}\n]+)\}', text[:a]):
        headings.append({'level':match[1], 'title':match[2][:200]})
    return {'status':'available', 'read_only':True, 'section_title':target.get('title', ''),
            'selection_start':a, 'selection_end':b, 'section_length':len(text),
            'preceding_headings':headings[-6:],
            'before':text[max(0, a-limit):a], 'after':text[b:b+limit],
            'before_truncated':a>limit, 'after_truncated':len(text)-b>limit,
            'notice':'仅用于判断章节目标、段落叙事角色及承上启下；位置不是角色标签。选区外内容不可修改，截断内容不足时按需查证，不猜测。'}


def resolve(folder, state, run_id, points):
    import latex_project as latex
    import synctex_mapping
    if not isinstance(points, list) or not 1 <= len(points) <= 256:
        raise ValueError('选区过长或为空，请缩小 PDF 段落选择范围')
    for point in points:
        if not isinstance(point, list) or len(point) != 3 or type(point[0]) is not int or any(type(n) not in (int, float) for n in point[1:]):
            raise ValueError('PDF 选择坐标无效')
    first = latex.inverse_search(folder, state, run_id, *points[0])
    mapping = json.loads((folder / '.latex/builds' / run_id / 'source-map.json').read_text())
    hits = [first] + [synctex_mapping.locate(mapping, *p) for p in points[1:]]
    if any(hit['path'] != first['path'] for hit in hits):
        raise ValueError('选区跨越多个 TeX 文件，请分别选择')
    raw = latex.source_path(folder, first['path']).read_bytes().decode('utf-8')
    lines = raw.splitlines(keepends=True)
    offsets = [0]
    for line in lines: offsets.append(offsets[-1] + len(line))
    positions = []
    for hit in hits:
        line = hit['line'] - 1
        if not 0 <= line < len(lines): raise ValueError('无法定位所选段落，请重新编译')
        # SyncTeX paragraph boxes can point at the blank line immediately after it.
        while line > 0 and not lines[line].strip(): line -= 1
        positions.append(offsets[line])
    section = next((s for s in state['sections'] if s.get('source_file') == first['path'] and
                    all(s['source_start'] <= pos < s['source_end'] for pos in positions)), None)
    if section is None: raise ValueError('选区跨越章节或不在正文块中，请缩小选择范围')
    text = section['text']
    # Blank lines inside environments do not split a source block. This preserves
    # complete equation/list/table environments when expanding to paragraph bounds.
    spans, start, offset, depth = [], 0, 0, 0
    for line in text.splitlines(keepends=True):
        code = re.split(r'(?<!\\)%', line, maxsplit=1)[0]
        if depth == 0 and not line.strip():
            if offset > start: spans.append((start, offset))
            start = offset + len(line)
        for token in re.finditer(r'\\(begin|end)\s*\{[^}]+\}', code):
            depth = max(0, depth + (1 if token[1] == 'begin' else -1))
        offset += len(line)
    if offset > start: spans.append((start, offset))
    chosen = []
    for pos in positions:
        local = pos - section['source_start']
        span = next((span for span in spans if span[0] <= local < span[1]), None)
        if span is None: raise ValueError('无法确定段落边界，请重新选择')
        chosen.append(span)
    a, b = min(s[0] for s in chosen), max(s[1] for s in chosen)
    if b-a > 24000: raise ValueError('所选源码过长，请缩小选择范围')
    return {'sectionId':section['id'], 'path':first['path'], 'start':a, 'end':b,
            'text':text[a:b], 'version':section['versions'][-1]['id'],
            'startLine':raw[:section['source_start']+a].count('\n')+1,
            'endLine':raw[:section['source_start']+b].rstrip('\r\n').count('\n')+1}


def validate(target, selection):
    if not target or target.get('format') != 'latex' or not isinstance(selection, dict):
        raise ValueError('段落选择仅适用于当前 LaTeX 章节')
    a, b, text = selection.get('start'), selection.get('end'), selection.get('text')
    if (type(a) is not int or type(b) is not int or not isinstance(text, str) or
        not 0 <= a < b <= len(target['text']) or b-a > 24000 or
        selection.get('version') != target['versions'][-1]['id'] or target['text'][a:b] != text):
        raise ValueError('选中段落已变化，请重新选择后发送')
    return {'start':a, 'end':b, 'text':text, 'version':selection['version'], 'path':target['source_file']}


def highlight(folder, state, run_id, section_id, start, end, version):
    """Return normalized PDF line rectangles for a complete selected source span."""
    import latex_project as latex
    import pymupdf
    compiled = latex.build_status(folder, state)['compiled']
    if not compiled or compiled['runId'] != run_id:
        raise ValueError('PDF 已更新，请等待预览刷新后重试')
    latex.refresh(folder, state)
    if compiled['sourceHash'] != state['latex']['sourceHash']:
        raise ValueError('源码已修改，请重新编译后定位')
    section = next((s for s in state['sections'] if s['id'] == section_id), None)
    if not section: raise ValueError('所选章节不存在')
    if type(start) is not int or type(end) is not int: raise ValueError('段落修改范围无效')
    validate(section, {'start':start,'end':end,'version':version,'text':section['text'][start:end]})
    raw = latex.source_path(folder, section['source_file']).read_bytes().decode('utf-8')
    a, b = section['source_start']+start, section['source_start']+end
    first_line, last_line = raw[:a].count('\n')+1, raw[:b].rstrip('\r\n').count('\n')+1
    mapping_path = folder/'.latex/builds'/run_id/'source-map.json'
    if not mapping_path.exists(): raise ValueError('请重新编译一次，以启用 PDF 双击定位')
    mapping = json.loads(mapping_path.read_text())
    rectangles=[]
    with pymupdf.open(folder/'.latex/compiled.pdf') as doc:
        for number, page in enumerate(doc,1):
            records=[r for r in mapping.get(str(number),[]) if r[0]==section['source_file'] and first_line<=r[1]<=last_line and not r[7]]
            if not records: continue
            # Require a source node inside the typeset line, rather than nearest
            # neighbor matching which could falsely highlight headers or footers.
            for block in page.get_text('dict',flags=pymupdf.TEXTFLAGS_DICT & ~pymupdf.TEXT_PRESERVE_IMAGES)['blocks']:
                for line in block.get('lines',[]):
                    box=pymupdf.Rect(line['bbox'])
                    if not any(box.x0-2<=r[3]<=box.x1+2 and box.y0<=((r[4]+r[6])/2)<=box.y1 for r in records):continue
                    box=box*page.rotation_matrix
                    rectangles.append([number,100*box.x0/page.rect.width,100*box.y0/page.rect.height,100*box.width/page.rect.width,100*box.height/page.rect.height])
    return {'runId':run_id,'rects':rectangles}
