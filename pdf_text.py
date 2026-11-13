"""Small, page-local text layers for the raster PDF preview."""
import pymupdf


def page_text(page):
    # Keep PDF content order (rather than sorting across columns) and omit image
    # payloads. Character boxes keep selection aligned with justified text.
    data=page.get_text('rawdict',flags=pymupdf.TEXTFLAGS_RAWDICT & ~pymupdf.TEXT_PRESERVE_IMAGES)
    blocks=[]
    for block in data['blocks']:
        if block['type']!=0:continue
        lines=[]
        for line in block['lines']:
            chars=[]
            for span in line['spans']:
                for char in span['chars']:
                    rect=pymupdf.Rect(char['bbox'])*page.rotation_matrix
                    if rect.is_empty:continue
                    chars.append([char['c'],*[round(v,4) for v in rect]])
            if chars:lines.append(chars)
        if lines:blocks.append(lines)
    return {'width':page.rect.width,'height':page.rect.height,'blocks':blocks}
