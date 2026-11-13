"""English UI resources, derived from shared source without changing user content."""
import json
import re
from pathlib import Path

CATALOG = json.loads((Path(__file__).parent / 'ui/translations-en.json').read_text())
CJK = re.compile(r'[\u4e00-\u9fff]')
LITERAL = re.compile(r'''(['"])((?:\\.|(?!\1).)*?)\1''')


def english_resource(name, source):
    if name.endswith('.js'):
        if name == 'preferences.js':
            # This page uses static HTML templates; user data is inserted with textContent.
            def template(match):
                html = re.sub(r'>([^<>]+)<', lambda m: '>' + CATALOG.get(m[1], m[1]) + '<', match[1])
                return '`' + html + '`'
            source = re.sub(r'`([^`]+)`', template, source)
        def literal(match):
            quote, original = match.groups()
            translated = CATALOG.get(original)
            if translated is None:
                return match[0]
            return quote + translated.replace(quote, '\\' + quote) + quote
        # Section classification must still recognize Chinese manuscript headings.
        lines = source.splitlines(keepends=True)
        source = ''.join(line if line.startswith('function strategySection(') else LITERAL.sub(literal, line) for line in lines)
        source = source.replace("'zh-CN'", "'en-US'")
        source = source.replace('notes should flag uncertain boundaries in Chinese', 'notes should flag uncertain boundaries in English')
    elif name.endswith('.html'):
        source = re.sub(r'>([^<>]+)<', lambda m: '>' + CATALOG.get(m[1], m[1]) + '<', source)
        source = re.sub(r'"([^"<>]+)"', lambda m: '"' + CATALOG.get(m[1], m[1]).replace('"', '&quot;') + '"', source)
        source = source.replace('lang="zh-CN"', 'lang="en"').replace('</code>。', '</code>.')
    if name == 'language.js':
        source = source.replace('/* ENGLISH_CATALOG */ {}', json.dumps(CATALOG, ensure_ascii=True))
    return source


def system_text(text):
    """Translate only application metadata; never drafts, prompts, or model output."""
    if not isinstance(text, str) or not CJK.search(text):
        return text
    if text in CATALOG:
        return CATALOG[text]
    suffix=' 已生成内容仅供预览，当前稿未改写。'
    if text.endswith(suffix):
        return system_text(text[:-len(suffix)])+' '+CATALOG[suffix.strip()]
    match=re.fullmatch(r'Gemini 请求失败（HTTP (\d+)）：(.*)',text)
    if match:
        return f'Gemini request failed (HTTP {match[1]}): '+system_text(match[2])
    match=re.fullmatch(r'Gemini 单轮生成达到本网站的时间上限（(\d+) 秒），已主动停止；这不代表 API 连接故障。请缩小本轮修改范围后重试。',text)
    if match:
        return f'Gemini reached this app’s per-generation time limit ({match[1]} seconds) and was stopped locally. This does not indicate an API connection failure. Reduce the scope of this request and retry.'
    match = re.fullmatch(r'(Gemini|OpenAI) 第 (\d+) 轮生成 · 已调用 (\d+(?:/\d+)?) 个工具', text)
    if match:
        return f'{match[1]} generation round {match[2]} · {match[3]} tools used'
    if text.startswith('开始：'):
        label, separator, detail = text[3:].partition(' · ')
        return 'Starting: ' + CATALOG.get(label, label) + separator + detail
    return text


def response_metadata(data):
    if not isinstance(data, dict):
        return data
    result = dict(data)
    for key in ('error',):
        if key in result:
            result[key] = system_text(result[key])
    for key in ('roles', 'sections'):
        if isinstance(result.get(key), dict):
            result[key] = {k: system_text(v) for k, v in result[key].items()}
    if isinstance(result.get('files'), list):
        result['files'] = [dict(item, title=system_text(item['title'])) if isinstance(item, dict) and 'title' in item else item for item in result['files']]
    if isinstance(result.get('items'), list):
        result['items'] = [dict(item, title=system_text(item['title'])) if isinstance(item, dict) and item.get('kind') in ('role','skill','memory') and 'title' in item else item for item in result['items']]
    if result.get('type') in ('activity', 'progress', 'tool') and 'message' in result:
        result['message'] = system_text(result['message'])
    return result
