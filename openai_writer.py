"""OpenAI Responses adapter for the writing graph's message format."""
import http.client
import json
import time
import urllib.error
import urllib.request
from gemini_stream import StreamError


def schema(value):
    if isinstance(value, list):
        return [schema(item) for item in value]
    if isinstance(value, dict):
        return {key: item.lower() if key == 'type' and isinstance(item, str) else schema(item)
                for key, item in value.items()}
    return value


def request_body(body, model):
    items = []
    for turn in body['contents']:
        if turn.get('openaiOutput'):
            items.extend(turn['openaiOutput'])
            continue
        text, images = [], []
        for part in turn['parts']:
            if 'text' in part and not part.get('thought'):
                text.append(part['text'])
            if 'functionCall' in part:
                call = part['functionCall']
                items.append({'type': 'function_call', 'call_id': call['id'], 'name': call['name'],
                              'arguments': json.dumps(call.get('args', {}))})
            if 'functionResponse' in part:
                response = part['functionResponse']
                items.append({'type': 'function_call_output', 'call_id': response['id'],
                              'output': json.dumps(response['response'], ensure_ascii=False)})
                for attachment in response.get('parts', []):
                    data = attachment.get('inlineData')
                    if data:
                        images.extend([{'type': 'input_text', 'text': data.get('displayName', 'Source page')},
                                       {'type': 'input_image', 'image_url':
                                        'data:' + data['mimeType'] + ';base64,' + data['data']}])
        if text or images:
            role = 'assistant' if turn['role'] == 'model' else 'user'
            if role == 'assistant':
                items.append({'role': role, 'content': '\n'.join(text)})
            else:
                content = [{'type': 'input_text', 'text': '\n'.join(text)}] if text else []
                items.append({'role': role, 'content': content + images})
    tools = [{'type': 'function', **schema(tool), 'strict': False}
             for group in body.get('tools', []) for tool in group.get('functionDeclarations', [])]
    result = {'model': model, 'input': items, 'stream': True, 'store': False,
              'include': ['reasoning.encrypted_content'],
              'instructions': '\n'.join(p['text'] for p in body.get('systemInstruction', {}).get('parts', []) if 'text' in p),
              'max_output_tokens': body.get('generationConfig', {}).get('maxOutputTokens', 32768)}
    if body.get('reasoningEffort'):
        result['reasoning']={'effort':body['reasoningEffort']}
    if tools:
        result.update(tools=tools, tool_choice='auto')
    return result


def http_error(error):
    hints = {400: '请求参数或模型接口不兼容。', 401: 'API Key 无效，请检查配置。',
             403: '没有模型访问权限。', 404: '模型不存在或账户无权使用。',
             429: '额度不足或达到速率限制。'}
    # Never expose upstream error text, which can echo credentials or manuscript content.
    return StreamError('http_' + str(error.code), 'OpenAI 请求失败（HTTP ' + str(error.code) +
                       '）：' + hints.get(error.code, '服务暂时不可用，请稍后重试。'))


def generate(key, model, body, timeout, on_text, check, on_status=None):
    request = urllib.request.Request('https://api.openai.com/v1/responses',
        headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + key},
        data=json.dumps(request_body(body, model)).encode(), method='POST')
    started = time.monotonic()
    pending = []
    completed = None
    chunks = characters = 0

    def report(stage):
        if on_status:
            on_status({'stage': stage, 'chunks': chunks, 'characters': characters,
                       'elapsed': round(time.monotonic() - started, 1)})

    def consume():
        nonlocal completed, chunks, characters
        if not pending:
            return
        payload = '\n'.join(pending)
        pending.clear()
        if payload == '[DONE]':
            return
        chunk = json.loads(payload)
        chunks += 1
        event = chunk.get('type')
        if event in {'error', 'response.failed', 'response.incomplete'}:
            raise StreamError('incomplete_output', 'OpenAI 未完成本轮输出，请检查额度或缩小修改范围后重试。')
        if event == 'response.refusal.delta':
            raise StreamError('refusal', 'OpenAI 未能处理本次请求，请调整要求后重试。')
        if event == 'response.output_text.delta':
            text = chunk.get('delta', '')
            characters += len(text)
            on_text(text)
        if event == 'response.completed':
            completed = chunk['response']
        report('text' if characters else 'tool' if event == 'response.function_call_arguments.delta' else 'receiving')

    check()
    report('requesting')
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            report('connected')
            for raw in response:
                check()
                if time.monotonic() - started > timeout:
                    raise StreamError('generation_deadline', 'OpenAI 本轮生成超时，请缩小修改范围后重试。')
                line = raw.decode('utf-8').rstrip('\r\n')
                if not line:
                    consume()
                    if completed is not None:
                        break
                elif line.startswith('data:'):
                    pending.append(line[5:].lstrip(' '))
            consume()
    except urllib.error.HTTPError as error:
        raise http_error(error) from None
    except (urllib.error.URLError, OSError, http.client.HTTPException):
        raise StreamError('connection_failed', 'OpenAI 连接失败或中断，请检查网络后重试。') from None
    except (json.JSONDecodeError, UnicodeDecodeError, KeyError, TypeError) as error:
        if isinstance(error, StreamError):
            raise
        raise StreamError('invalid_response', 'OpenAI 响应格式异常，请重试。') from None
    if completed is None or completed.get('status') != 'completed':
        raise StreamError('incomplete_output', 'OpenAI 输出中断，未收到完整结果，请重试。')
    parts = []
    output = completed.get('output', [])
    try:
        for item in output:
            if item['type'] == 'message':
                for content in item.get('content', []):
                    if content['type'] == 'refusal':
                        raise StreamError('refusal', 'OpenAI 未能处理本次请求，请调整要求后重试。')
                    if content['type'] == 'output_text':
                        parts.append({'text': content['text']})
            elif item['type'] == 'function_call':
                args = json.loads(item['arguments'])
                if not item.get('call_id') or not item.get('name') or not isinstance(args, dict):
                    raise ValueError()
                parts.append({'functionCall': {'id': item['call_id'], 'name': item['name'], 'args': args}})
    except StreamError:
        raise
    except (ValueError, TypeError, KeyError):
        raise StreamError('invalid_tool_call', 'OpenAI 工具参数不完整，尚未执行工具，请重试。') from None
    if not parts:
        raise StreamError('empty_response', 'OpenAI 未返回可用内容，请重试。')
    check()
    report('completed')
    usage = completed.get('usage') or {}
    return {'candidates': [{'content': {'role': 'model', 'parts': parts, 'openaiOutput': output}, 'finishReason': 'STOP'}],
            'usageMetadata': {'promptTokenCount': usage.get('input_tokens', 0),
                              'candidatesTokenCount': usage.get('output_tokens', 0),
                              'totalTokenCount': usage.get('total_tokens', 0),
                              'thoughtsTokenCount': (usage.get('output_tokens_details') or {}).get('reasoning_tokens', 0)}}
