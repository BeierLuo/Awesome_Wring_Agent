"""Local reference papers and cached, source-anchored writing-style examples."""
import hashlib,json,re,threading,uuid,fcntl
from pathlib import Path
import pymupdf

BASE=Path(__file__).resolve().parent
ROOT=BASE/'style-library'
LOCK=threading.RLock()
ANALYZING=set()
ROLES={'background':'背景与重要性','gap':'研究缺口','motivation':'动机与问题','contribution':'贡献概述','method':'方法解释','experiment':'实验设置','result':'结果解读','limitation':'局限与讨论','conclusion':'结论与总结'}

def write(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp');tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2));tmp.replace(path)
def paper_path(root,pid):
    if not isinstance(pid,str) or not re.fullmatch('[0-9a-f]{64}',pid):raise ValueError('参考论文 ID 无效')
    p=Path(root)/pid
    if p.is_symlink():raise ValueError('不支持论文链接目录')
    return p

def read(root,pid):
    path=paper_path(root,pid)/'paper.json'
    if path.is_symlink():raise ValueError('不支持论文元数据链接')
    return json.loads(path.read_text())
def summary(p):
    return {k:p[k] for k in ['id','name','pages','paragraphs','batches','done','status']}
def catalog(root=ROOT):
    Path(root).mkdir(parents=True,exist_ok=True)
    return [summary(read(root,p.name)) for p in sorted(Path(root).iterdir()) if re.fullmatch('[0-9a-f]{64}',p.name) and not p.is_symlink() and (p/'paper.json').exists()]
def ingest(raw,name,root=ROOT):
    if not isinstance(raw,bytes) or not 0<len(raw)<=25*1024*1024 or b'%PDF-' not in raw[:1024]:raise ValueError('请上传25 MB以内的 PDF')
    pid=hashlib.sha256(raw).hexdigest();folder=paper_path(root,pid)
    with LOCK:
        if (folder/'paper.json').exists():return summary(read(root,pid))
        paragraphs=[]
        try:document=pymupdf.open(stream=raw,filetype='pdf')
        except (pymupdf.FileDataError,RuntimeError):raise ValueError('无法解析 PDF，请检查文件是否完整') from None
        with document as doc:
            if doc.needs_pass or len(doc)>200:raise ValueError('请使用未加密、200页以内的 PDF')
            page_count=len(doc)
            for number,page in enumerate(doc,1):
                # PDF text blocks are source excerpts, not guaranteed semantic paragraph boundaries.
                for block in page.get_text('blocks',sort=True):
                    text=block[4].strip()
                    if len(text)<60:continue
                    for offset in range(0,len(text),4500):
                        fragment=text[offset:offset+4500]
                        paragraphs.append({'id':f'p{number}-b{len(paragraphs)+1}','page':number,'text':fragment})
        if not paragraphs:raise ValueError('没有可提取文字，请先给扫描 PDF 添加 OCR 文字层')
        if sum(len(x['text']) for x in paragraphs)>800000:raise ValueError('论文文字过多，请缩小 PDF')
        chunks=[];chunk=[];size=0
        for p in paragraphs:
            if size+len(p['text'])>18000 and chunk:chunks.append(chunk);chunk=[];size=0
            chunk.append(p);size+=len(p['text'])
        if chunk:chunks.append(chunk)
        paper={'id':pid,'name':Path(name).name[:240],'pages':page_count,'paragraphs':len(paragraphs),'batches':len(chunks),'done':0,'status':'待分析','chunks':chunks,'analyses':[]}
        folder.mkdir(parents=True,exist_ok=True);(folder/'original.pdf').write_bytes(raw);write(folder/'paper.json',paper)
        return summary(paper)

SCHEMA={'type':'object','additionalProperties':False,'properties':{
 'overview':{'type':'string'},'examples':{'type':'array','items':{'type':'object','additionalProperties':False,'properties':{
 'paragraph_id':{'type':'string'},'role':{'type':'string','enum':list(ROLES)},'section':{'type':'string'},'purpose':{'type':'string'},'logic':{'type':'string'},'sentence_moves':{'type':'array','items':{'type':'string'}},'wording':{'type':'string'}},'required':['paragraph_id','role','section','purpose','logic','sentence_moves','wording']}}},'required':['overview','examples']}

def analyze_next(root,pid,generate,instructions):
    with LOCK:
        if pid in ANALYZING:raise ValueError('这篇论文正在分析，请稍候')
        p=read(root,pid)
        if p['done']==p['batches']:return summary(p)
        ANALYZING.add(pid)
    handle=(paper_path(root,pid)/'analysis.lock').open('a')
    try:
        try:fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise ValueError('这篇论文正在分析，请稍候') from None
        p=read(root,pid)
        if p['done']==p['batches']:return summary(p)
        chunk=p['chunks'][p['done']]
        body={'store':False,'instructions':instructions,'input':[{'role':'user','content':[{'type':'input_text','text':json.dumps({'paper':p['name'],'batch':p['done']+1,'batches':p['batches'],'excerpts':chunk},ensure_ascii=False)}]}],'max_output_tokens':10000,'text':{'format':{'type':'json_schema','name':'writing_style','strict':True,'schema':SCHEMA}}}
        response=generate(body)
        if response.get('status','completed')!='completed':raise ValueError('风格分析未完整生成，可重试当前批次')
        text=''.join(c.get('text','') for x in response.get('output',[]) for c in x.get('content',[]) if c.get('type')=='output_text')
        result=json.loads(text);ids={x['id'] for x in chunk}
        if not isinstance(result.get('overview'),str) or not isinstance(result.get('examples'),list):raise ValueError('风格分析格式无效')
        if len(result['overview'])>2400 or len(result['examples'])>12:raise ValueError('分析过长或未按范例结构返回，未保存，可重试')
        for e in result['examples']:
            if e.get('paragraph_id') not in ids or e.get('role') not in ROLES:raise ValueError('分析包含无法核对的原文来源，未保存')
            for key in ['section','purpose','logic','wording']:
                if not isinstance(e.get(key),str) or len(e[key])>6000:raise ValueError('风格分析字段无效')
            if not isinstance(e.get('sentence_moves'),list) or any(not isinstance(s,str) for s in e['sentence_moves']):raise ValueError('句子分析格式无效')
        with LOCK:
            p['analyses'].append(result);p['done']+=1;p['status']='已分析' if p['done']==p['batches'] else '分析中（可继续）';write(paper_path(root,pid)/'paper.json',p)
        return summary(p)
    finally:
        handle.close()
        with LOCK:ANALYZING.discard(pid)

def selected(folder):
    path=Path(folder)/'style-reference.json'
    return json.loads(path.read_text()) if path.exists() else {'paper_ids':[],'role':'','query':''}
def save_selection(folder,root,data):
    ids=data.get('paper_ids',[]);role=data.get('role','');query=data.get('query','')
    if not isinstance(ids,list) or len(ids)>3 or len(set(ids))!=len(ids):raise ValueError('最多指定3篇参考论文')
    for pid in ids:read(root,pid)
    if not isinstance(role,str) or role not in {'',*ROLES} or not isinstance(query,str) or len(query)>1000:raise ValueError('写作参考设置无效')
    result={'paper_ids':ids,'role':role,'query':query};write(Path(folder)/'style-reference.json',result);return result

def search(root,ids=None,role='',query='',limit=4):
    if not isinstance(role,str) or role not in {'',*ROLES}:raise ValueError('段落作用无效')
    if not isinstance(query,str) or len(query)>1000:raise ValueError('检索要求最多1000字符')
    if ids is None:ids=[p['id'] for p in catalog(root)]
    if not isinstance(ids,list) or len(ids)>100:raise ValueError('参考论文范围无效')
    terms=set(re.findall(r'[a-z0-9]{2,}',query.lower()))
    for phrase in re.findall(r'[\u4e00-\u9fff]{2,}',query):terms.update(phrase[i:i+2] for i in range(len(phrase)-1))
    results=[];pending=[]
    for pid in ids:
        p=read(root,pid);paragraphs={x['id']:x for c in p['chunks'] for x in c}
        if p['done']<p['batches']:pending.append({'paper_id':pid,'done':p['done'],'batches':p['batches']})
        for analysis in p['analyses']:
            for e in analysis['examples']:
                if role and e['role']!=role:continue
                source=paragraphs[e['paragraph_id']];haystack=json.dumps(e,ensure_ascii=False).lower()+' '+source['text'].lower()
                score=sum(term in haystack for term in terms)
                results.append({'paper_id':pid,'paper':p['name'],'source_id':pid[:12]+':'+source['id'],'page':source['page'],'text':source['text'][:2800],'text_truncated':len(source['text'])>2800,**e,'score':score})
    results.sort(key=lambda x:(-x['score'],x['page']))
    # Prefer varied papers, then fill the remaining slots.
    chosen=[];seen=set()
    for e in results:
        if e['paper_id'] not in seen:chosen.append(e);seen.add(e['paper_id'])
        if len(chosen)>=limit:break
    for e in results:
        if len(chosen)>=limit:break
        if e not in chosen:chosen.append(e)
    for e in chosen:
        for key in ['purpose','logic','wording']:e[key]=e[key][:800]
        e['sentence_moves']=[s[:200] for s in e['sentence_moves'][:8]]
    return {'examples':chosen,'pending':pending,'notice':'参考原文只用于表达与论证结构，不是当前论文的事实依据。PDF 文本块可能跨段或拆段，请对照原 PDF 核查。'}

def compact(result):
    for e in result['examples']:
        e['text_truncated']=e.get('text_truncated',False) or len(e['text'])>1400
        e['text']=e['text'][:1400]
        for key in ['purpose','logic','wording']:e[key]=e[key][:350]
        e['sentence_moves']=[s[:140] for s in e['sentence_moves'][:6]]
    return result

def context(folder,root=ROOT,settings_override=None):
    settings=selected(folder) if settings_override is None else settings_override
    if not settings['paper_ids']:return None
    papers=[summary(read(root,p)) for p in settings['paper_ids']]
    examples=compact(search(root,settings['paper_ids'],settings['role'],settings['query'],3))
    return {'papers':papers,'paragraph_role':settings['role'],'request':settings['query'],**examples}
