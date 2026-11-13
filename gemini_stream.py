"""Gemini SSE transport: retain model parts, expose only visible answer text."""
import json
import socket
import ssl
import http.client
import time
import urllib.request
import urllib.error


class StreamError(ValueError):
    def __init__(self, code, message):
        self.code=code
        super().__init__(message+' 已生成内容仅供预览，当前稿未改写。')


def transport_error(error, connected=False):
    if isinstance(error, urllib.error.HTTPError):
        code=error.code
        hints={400:'请求参数无效，请检查模型和请求配置。',
               401:'认证失败，请检查 API Key 或登录凭据。',
               403:'访问被拒绝，请检查模型权限、API 启用状态及 Key 限制。',
               404:'未找到模型或接口，请检查模型名称、项目和地区。',
               429:'请求受限，可能达到速率或配额限制，请检查额度并稍后重试。'}
        hint=hints.get(code,'服务端暂时异常，请稍后重试。' if code>=500 else '请求失败，请检查 API 配置。')
        return StreamError('http_'+str(code),'Gemini 请求失败（HTTP '+str(code)+'）：'+hint)
    reason=error.reason if isinstance(error,urllib.error.URLError) else error
    if isinstance(reason,TimeoutError):
        return StreamError('read_timeout' if connected else 'connection_timeout',
            'Gemini 响应等待超时：已连接，但等待后续数据超过时限，请稍后重试。' if connected else
            'Gemini 连接等待超时：未能及时建立连接或收到响应头，请检查网络、代理后重试。')
    if isinstance(reason,socket.gaierror):
        return StreamError('dns_error','Gemini 域名解析失败，请检查网络、DNS 或代理设置。')
    if isinstance(reason,ssl.SSLError):
        return StreamError('tls_error','Gemini 安全连接失败，请检查证书、系统时间或代理设置。')
    if isinstance(reason,ConnectionRefusedError):
        return StreamError('connection_refused','Gemini 连接被拒绝，请检查网络或代理服务是否可用。')
    if connected:
        return StreamError('connection_interrupted','Gemini 传输连接中断，未收到完整结果，请检查网络或代理后重试。')
    return StreamError('connection_failed','Gemini 网络连接失败，请检查网络、代理和服务可用性后重试。')


def generate(url, headers, body, timeout, on_text, check, on_status=None):
    url=url.replace(':generateContent', ':streamGenerateContent')
    url+=('&' if '?' in url else '?')+'alt=sse'
    request=urllib.request.Request(url,headers=headers,data=json.dumps(body).encode(),method='POST')
    result={'candidates':[]};candidate={'content':{'role':'model','parts':[]}}
    started=time.monotonic();pending=[];chunks=0;characters=0;last_status=-1;last_stage=None
    def report(stage,force=False):
        nonlocal last_status,last_stage
        if on_status is None:return
        elapsed=time.monotonic()-started
        if force or stage!=last_stage or elapsed-last_status>=1:
            on_status({'stage':stage,'chunks':chunks,'characters':characters,'elapsed':round(elapsed,1)})
            last_status=elapsed;last_stage=stage
    report('requesting',True)
    def consume():
        nonlocal chunks,characters
        if not pending:return
        payload='\n'.join(pending);pending.clear()
        if payload=='[DONE]':return
        chunk=json.loads(payload);chunks+=1
        stage='receiving'
        if chunk.get('error'):
            code=chunk['error'].get('code',502) if isinstance(chunk['error'],dict) else 502
            if not isinstance(code,int):code=502
            raise transport_error(urllib.error.HTTPError('',code,'',{},None),True)
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
                    characters+=len(part['text']);on_text(part['text']);stage='text'
                elif part.get('functionCall'):stage='tool'
        report('text' if characters else stage)
    connected=False
    try:
        with urllib.request.urlopen(request,timeout=timeout) as response:
            connected=True;report('connected',True)
            for raw in response:
                check()
                if time.monotonic()-started>timeout:
                    raise StreamError('generation_deadline','Gemini 单轮生成达到本网站的时间上限（'+str(round(timeout))+' 秒），已主动停止；这不代表 API 连接故障。请缩小本轮修改范围后重试。')
                line=raw.decode('utf-8').rstrip('\r\n')
                if not line:consume()
                elif line.startswith('data:'):pending.append(line[5:].lstrip(' '))
            consume()
    except (urllib.error.URLError,OSError,http.client.HTTPException) as error:
        raise transport_error(error,connected) from None
    except (json.JSONDecodeError,UnicodeDecodeError):
        raise StreamError('invalid_response','Gemini 响应格式异常，无法解析完整结果，请重试。') from None
    if not result['candidates']:
        raise StreamError('empty_response','Gemini 未返回可用内容，请检查请求或内容限制后重试。')
    if not candidate.get('finishReason'):
        raise StreamError('incomplete_output','Gemini 输出中途断开：未收到完成标记，请重试。')
    report('completed',True)
    # Join adjacent plain text chunks without altering function calls or signatures.
    parts=[]
    for part in candidate['content']['parts']:
        if set(part)=={'text'} and parts and set(parts[-1])=={'text'}:parts[-1]['text']+=part['text']
        else:parts.append(part.copy())
    candidate['content']['parts']=parts
    return result
