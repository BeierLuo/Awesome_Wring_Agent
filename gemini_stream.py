"""Gemini SSE transport: retain model parts, expose only visible answer text."""
import json
import time
import urllib.request
import urllib.error


def generate(url, headers, body, timeout, on_text, check):
    url=url.replace(':generateContent', ':streamGenerateContent')
    url+=('&' if '?' in url else '?')+'alt=sse'
    request=urllib.request.Request(url,headers=headers,data=json.dumps(body).encode(),method='POST')
    result={'candidates':[]};candidate={'content':{'role':'model','parts':[]}}
    started=time.monotonic();pending=[]
    def consume():
        if not pending:return
        payload='\n'.join(pending);pending.clear()
        if payload=='[DONE]':return
        chunk=json.loads(payload)
        if chunk.get('error'):raise ValueError('Gemini 流式生成失败；当前稿未改写。')
        for key in ('usageMetadata','promptFeedback','modelVersion'):
            if key in chunk:result[key]=chunk[key]
        for item in chunk.get('candidates',[]):
            if item.get('index',0)!=0:continue
            result['candidates']=[candidate]
            for key,value in item.items():
                if key!='content':candidate[key]=value
            for part in item.get('content',{}).get('parts',[]):
                candidate['content']['parts'].append(part)
                if isinstance(part.get('text'),str) and not part.get('thought'):
                    on_text(part['text'])
    with urllib.request.urlopen(request,timeout=timeout) as response:
        for raw in response:
            check()
            if time.monotonic()-started>timeout:raise TimeoutError('Gemini 流式响应超时')
            line=raw.decode('utf-8').rstrip('\r\n')
            if not line:consume()
            elif line.startswith('data:'):pending.append(line[5:].lstrip(' '))
        consume()
    if result['candidates'] and not candidate.get('finishReason'):
        raise ValueError('Gemini 输出中途断开；预览不是完整修改稿，请重试。')
    # Join adjacent plain text chunks without altering function calls or signatures.
    parts=[]
    for part in candidate['content']['parts']:
        if set(part)=={'text'} and parts and set(parts[-1])=={'text'}:parts[-1]['text']+=part['text']
        else:parts.append(part.copy())
    candidate['content']['parts']=parts
    return result
