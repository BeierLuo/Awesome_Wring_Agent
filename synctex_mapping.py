"""Read Tectonic's SyncTeX v1 records for local PDF-to-source navigation.

Coordinates are PDF points from the top left. Only project-owned inputs are
indexed; package files and generated files are deliberately excluded.
"""
import gzip
import math
import re
from pathlib import Path

RECORD = re.compile(r'^([\[(hvgkx$])\s*(\d+),(\d+)(?:,(-?\d+))?:(-?\d+),(-?\d+)(?::(-?\d+),?(-?\d+)?,?(-?\d+)?)?')


def read_mapping(path, source_root, allowed):
    with gzip.open(path, 'rt', encoding='utf-8', errors='replace') as stream:
        text = stream.read(64 * 1024 * 1024 + 1)
    if len(text) > 64 * 1024 * 1024:
        raise ValueError('SyncTeX 数据过大')
    inputs, pages, stack = {}, {}, []
    unit, mag, ox, oy, page = 1, 1000, 0, 0, None
    root = Path(source_root).resolve()
    for record in text.splitlines():
        if record.startswith('Input:'):
            _, tag, name = record.split(':', 2)
            if not name:
                continue
            candidate = (root / name).resolve()
            if candidate.is_relative_to(root):
                name = candidate.relative_to(root).as_posix()
                if name in allowed:
                    inputs[int(tag)] = name
        elif record.startswith(('Unit:', 'Magnification:', 'X Offset:', 'Y Offset:')):
            key, value = record.split(':', 1)
            if key == 'Unit': unit = int(value)
            elif key == 'Magnification': mag = int(value)
            elif key == 'X Offset': ox = int(value)
            else: oy = int(value)
        elif record.startswith('Postamble:'):
            break
        elif record.startswith('{'):
            page = int(record[1:]); stack = []
        elif record.startswith('}'):
            page = None
        elif record in (')', ']'):
            if stack: stack.pop()
        elif page is not None:
            match = RECORD.match(record)
            if not match: continue
            kind, tag, line, column, x, y, width, height, depth = match.groups()
            factor = unit * mag / 1000 / 65781.76
            x, y = int(x)*factor + ox*unit/65781.76, int(y)*factor + oy*unit/65781.76
            width, height, depth = [int(v or 0)*factor for v in (width, height, depth)]
            parent = next((box for box in reversed(stack) if box[0] == '('), None)
            top, bottom = (y-height, y+depth) if kind in '[(hv' else (parent[1], parent[2]) if parent else (y-8, y+2)
            if kind in '[(': stack.append((kind, top, bottom))
            name = inputs.get(int(tag))
            if not name or int(line) < 1 or kind in '[v': continue
            # Leaf records retain the actual input line, unlike paragraph boxes
            # which often point to the following blank line / end of paragraph.
            left, right = (min(x, x+width), max(x, x+width)) if kind in '(h' else (x, x)
            pages.setdefault(str(page), []).append([name, int(line), max(0, int(column or 0)), left, top, right, bottom, kind in '(h'])
    return pages


def locate(pages, page, x, y):
    if not all(math.isfinite(v) and v >= 0 for v in (x, y)) or page < 1:
        raise ValueError('PDF 定位坐标无效')
    records = pages.get(str(page), [])
    if not records: raise ValueError('此页面没有可定位的源码')
    boxes = [r for r in records if r[7] and r[6] > r[4] and r[5] > r[3]]
    if boxes:
        def box_score(r):
            dx=max(r[3]-x,0,x-r[5]);dy=max(r[4]-y,0,y-r[6])
            return (dx*dx+dy*dy, (r[5]-r[3])*(r[6]-r[4]))
        box=min(boxes,key=box_score)
        leaves=[r for r in records if not r[7] and box[3]-1<=r[3]<=box[5]+1 and box[4]-1<=r[4] and r[6]<=box[6]+1]
        records=leaves or [box]
    else:
        records = [r for r in records if not r[7]] or records
    def score(r):
        dx = max(r[3]-x, 0, x-r[5]); dy = max(r[4]-y, 0, y-r[6])
        # Prefer actual line records within the nearest typeset line.
        return (dy, dx, abs((r[4]+r[6])/2-y))
    best = min(records, key=score)
    return {'path': best[0], 'line': best[1], 'column': best[2]}
