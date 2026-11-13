"""Small, source-backed style memories and section-specific writing plans."""
import hashlib,json,re,uuid
from pathlib import Path
import style_library as library

SECTIONS={'abstract':'Abstract','introduction':'Introduction','related_work':'Related Work','preliminary':'Preliminary','motivation':'Motivation','method':'Method','experiments':'Experiments','results':'Results','ablation':'Ablation','discussion':'Discussion','limitations':'Limitations','conclusion':'Conclusion','appendix':'Appendix','references':'References'}
AUTHORS={'hongxin':'Hongxin Wei','xuefeng':'Xuefeng Du'}
GLOBAL='''# 写作策略记忆导航
先确认当前章节的写作任务、论文的 hook 和贡献；缺少依据时提出备选路线，不编造论文定位。
按需读取 authors/<作者>/<章节>.md；写作风格记忆只读当前章节，不跨章节补例；查证论文事实另用资料助理。
这些是有限论文样本中的写作规律，不是作者固有属性；共同作者、领域和投稿年份可能影响风格。
规则必须有适用条件与原文来源。策略和可迁移规律保存在记忆中；原文、数据和全文保持在论文库，不重复抄入记忆。
需要例句或具体论证方式时用 find_style_examples 回查原文。参考论文不提供当前论文的实验事实。
GPT 给出的候选方案不是已验证结论；用户选定后才保存为当前章节计划，正文仍需用户确认采用。
'''

SECTION_PATTERNS={
    'abstract':r'\babstract\b|摘要',
    'introduction':r'\bintro(?:duction)?\b|引言|绪论',
    'related_work':r'\brelated[ _-]+work\b|相关工作',
    'preliminary':r'\bpreliminar(?:y|ies)\b|\bbackground\b|\bproblem (?:setup|formulation)\b|预备|背景|问题设定',
    'motivation':r'\bmotivation\b|动机',
    'method':r'\bmethod(?:s|ology)?\b|\bapproach\b|\bframework\b|方法',
    'experiments':r'\bexperiment(?:s|al)?\b|\bevaluation\b|实验|评估',
    'results':r'\bresults?\b|结果',
    'ablation':r'\bablation\b|消融',
    'discussion':r'\bdiscussion\b|讨论',
    'limitations':r'\blimitations?\b|局限',
    'conclusion':r'\bconclusions?\b|结论|总结',
    'appendix':r'\bappendi(?:x|ces)\b|\bsupplement(?:ary)?\b|附录|补充材料',
    'references':r'\breferences\b|\bbibliography\b|参考文献',
}
def section_key(title,default=None):
    t=(title or '').strip().lower()
    if t in SECTIONS:return t
    matches=[(match.start(),key) for key,pattern in SECTION_PATTERNS.items() if (match:=re.search(pattern,t))]
    # Prefer the named parent heading, not a later mention of another section.
    return min(matches)[1] if matches else default
def author_of(p):
    name=p['name'].lower()
    return 'hongxin' if 'hongxin' in name else 'xuefeng' if 'xuefeng' in name else None

def root_path(root):return Path(root)/'memory'
def ensure(root):
    p=root_path(root);p.mkdir(parents=True,exist_ok=True)
    if not (p/'global.md').exists():(p/'global.md').write_text(GLOBAL)
def key_path(root,author,section):
    if not isinstance(author,str) or not isinstance(section,str) or author not in AUTHORS or section not in SECTIONS:raise ValueError('请选择已支持的作者风格和章节')
    p=root_path(root)/'authors'/author/(section+'.md')
    if any(x.is_symlink() for x in [p,p.parent,p.parent.parent,root_path(root)]):raise ValueError('不支持记忆文件链接')
    return p
def read(root,author,section):
    p=key_path(root,author,section);text=p.read_text() if p.exists() else ''
    if len(text)>7000:raise ValueError('章节风格记忆超过7000字符，请精简后使用')
    return {'author':author,'section':section,'text':text,'exists':p.exists(),'sha256':hashlib.sha256(text.encode()).hexdigest(),'path':str(p)}
def save(root,author,section,text,expected):
    if not isinstance(text,str) or len(text)>7000 or '\x00' in text:raise ValueError('每份章节记忆最多7000字符')
    current=read(root,author,section)
    if current['sha256']!=expected:raise ValueError('记忆已更新，请重新读取后再保存')
    p=key_path(root,author,section);p.parent.mkdir(parents=True,exist_ok=True)
    if p.exists():
        backup=root_path(root)/'history'/uuid.uuid4().hex/(author+'-'+section+'.md');backup.parent.mkdir(parents=True,exist_ok=True);backup.write_text(current['text'])
    temp=p.with_suffix('.tmp');temp.write_text(text);temp.replace(p);return read(root,author,section)

def examples(root,author,section):
    result=[]
    for meta in library.catalog(root):
        if author and author_of(meta)!=author:continue
        p=library.read(root,meta['id']);original={x['id']:x for c in p['chunks'] for x in c}
        for batch in p['analyses']:
            for e in batch['examples']:
                if section_key(e.get('section'))!=section:continue
                src=original[e['paragraph_id']]
                result.append({'source_id':meta['id'][:12]+':'+src['id'],'paper_id':meta['id'],'paper':meta['name'],'page':src['page'],'section':e['section'],'role':e['role'],'purpose':e['purpose'][:500],'logic':e['logic'][:600],'wording':e['wording'][:500],'sentence_moves':e['sentence_moves'][:6],'text':src['text'][:1500]})
    # Round-robin across papers to avoid letting one paper dominate a profile.
    groups={}
    for e in result:groups.setdefault(e['paper_id'],[]).append(e)
    ordered=[]
    while any(groups.values()):
        for items in groups.values():
            if items:ordered.append(items.pop(0))
    return ordered[:18]

def json_result(generate,instructions,data,schema,name):
    result=generate({'store':False,'instructions':instructions,'input':[{'role':'user','content':[{'type':'input_text','text':json.dumps(data,ensure_ascii=False)}]}],'max_output_tokens':10000,'text':{'format':{'type':'json_schema','name':name,'strict':True,'schema':schema}}})
    if result.get('status','completed')!='completed':raise ValueError('GPT 回复未完成，请重试；已有记忆保留')
    raw=''.join(c.get('text','') for o in result.get('output',[]) for c in o.get('content',[]) if c.get('type')=='output_text')
    return json.loads(raw)
def obj(props):return {'type':'object','additionalProperties':False,'properties':props,'required':list(props)}
STR={'type':'string'}
STRINGS={'type':'array','items':STR}
RULE_SCHEMA=obj({'summary':STR,'rules':{'type':'array','items':obj({'rule':STR,'when':STR,'avoid':STR,'source_ids':STRINGS})},'uncertainties':STRINGS})

def build(root,author,section,generate,instructions):
    ensure(root);current=read(root,author,section);samples=examples(root,author,section)
    if not samples:
        text=f'# {AUTHORS[author]} / {SECTIONS[section]}\n\n当前缓存没有足够的对应章节范例，不能推断写作规则。可回查论文原文或补充样本。\n'
    else:
        result=json_result(generate,instructions,{'author_sample':AUTHORS[author],'section':SECTIONS[section],'examples':samples},RULE_SCHEMA,'section_style_rules')
        known={e['source_id']:e for e in samples}
        if not 1<=len(result['rules'])<=6 or len(result['summary'])>1000:raise ValueError('规则数量或摘要长度无效')
        lines=[f'# {AUTHORS[author]} / {SECTIONS[section]}','',result['summary'],'','以下为样本归纳，未证明是作者独有偏好；请按适用条件使用。','']
        for i,rule in enumerate(result['rules'],1):
            if not rule['source_ids'] or any(x not in known for x in rule['source_ids']):raise ValueError('规则缺少可核对的来源')
            lines.extend([f'## {i}. '+rule['rule'],'适用：'+rule['when'],'避免：'+rule['avoid'],'来源：'+'；'.join(known[x]['paper']+' 第 '+str(known[x]['page'])+' 页 ['+x+']' for x in dict.fromkeys(rule['source_ids'])),''])
        lines+=['## 不确定性',*result['uncertainties']];text='\n'.join(lines)
    return save(root,author,section,text,current['sha256'])

def settings(folder):
    p=Path(folder)/'writing-strategy.json'
    return json.loads(p.read_text()) if p.exists() else {'mode':'auto','goal':''}
def set_settings(folder,mode,goal):
    if mode not in {'auto','hongxin','xuefeng','off'} or not isinstance(goal,str) or len(goal)>2000:raise ValueError('写作策略设置无效')
    value={'mode':mode,'goal':goal,'section_types':settings(folder).get('section_types',{})};library.write(Path(folder)/'writing-strategy.json',value)
    library.write(Path(folder)/'style-reference.json',{'paper_ids':[],'role':'','query':''})
    return value
def set_section_type(folder,state,section_id,section):
    if not isinstance(section,str) or section not in SECTIONS:raise ValueError('请选择已支持的章节类型')
    if not isinstance(section_id,str) or not any(s['id']==section_id for s in state['sections']):raise ValueError('请先选择当前章节')
    config=settings(folder)
    config.setdefault('section_types',{})[section_id]=section
    library.write(Path(folder)/'writing-strategy.json',config)
    return config
def plan_path(folder,section):
    if section not in SECTIONS:raise ValueError('章节无效')
    p=Path(folder)/'memory/writing'/f'{section}.json'
    if any(x.is_symlink() for x in [p,p.parent,p.parent.parent]):raise ValueError('不支持计划文件链接')
    return p

def dashboard(root,folder,title,target=None):
    ensure(root);config=settings(folder)
    if config['mode']=='off':return None
    section=config.get('section_types',{}).get(target['id'],section_key(title)) if target else section_key(title)
    if section not in SECTIONS:
        return {'global':GLOBAL,'mode':config['mode'],'current_section':None,'goal':config['goal'],'available_memories':[], 'selected_plan':None,'pending_options':None,'notice':'当前章节类型未确认，请先选择章节类型；不会默认使用 Introduction 或跨章节参考。'}
    path=plan_path(folder,section)
    plan=json.loads(path.read_text()) if path.exists() else None
    if plan and target and plan.get('section_id')!=target['id']:plan=None
    proposal_file=plan_path(folder,section).with_name(section+'-proposal.json')
    proposal=json.loads(proposal_file.read_text()) if proposal_file.exists() else None
    if proposal and target and proposal.get('section_id')!=target['id']:proposal=None
    pending={'id':proposal['id'],'options':[{'title':o['title'],'hook':o['hook'][:250]} for o in proposal['options']],'status':'GPT 候选，未被用户选定'} if proposal else None
    global_text=(root_path(root)/'global.md').read_text()
    return {'global':global_text[:2200],'mode':config['mode'],'current_section':section,'goal':config['goal'],'available_memories':[{'author':a,'section':section,'available':read(root,a,section)['exists']} for a in AUTHORS], 'selected_plan':plan,'pending_options':pending,'notice':'每轮只给目录与当前章节计划；规则文件和例句按需读取。计划中的 hook 是写作假设，以最新原稿事实为准。'}

PLAN_SCHEMA=obj({'diagnosis':STR,'missing_information':STRINGS,'options':{'type':'array','items':obj({'title':STR,'author':{'type':'string','enum':['hongxin','xuefeng','mixed']},'hook':STR,'contribution_framing':STR,'paragraph_plan':STRINGS,'why_fit':STR,'risks':STRINGS,'paper_ids':STRINGS,'source_ids':STRINGS})}})

def recommend(root,folder,state,target,section,goal,mode,generate,instructions):
    if mode not in {'auto','hongxin','xuefeng'} or section not in SECTIONS or not isinstance(goal,str) or len(goal)>2000:raise ValueError('写作任务无效')
    authors=list(AUTHORS) if mode=='auto' else [mode]
    memories=[read(root,a,section) for a in authors]
    pool=[]
    for a in authors:pool.extend(examples(root,a,section)[:8])
    # Abstract/hook cards let GPT compare argument shape, rather than topic words alone.
    catalog=[]
    for p in library.catalog(root):
        if mode!='auto' and author_of(p)!=mode:continue
        data=library.read(root,p['id']);first=data['analyses'][0] if data['analyses'] else None
        catalog.append({'id':p['id'],'name':p['name'],'author_sample':author_of(p),'argument_overview':first['overview'][:900] if first else '尚未分析'})
    catalog=[p for p in catalog if p['id'] in {e['paper_id'] for e in pool}]
    if not pool:raise ValueError('该作者/章节暂无足够范例，请先补充对应论文分析，或选择其他章节')
    paper_abstract=next((s['text'][:5000] for s in state['sections'] if section_key(s['title'])=='abstract' and s.get('initialized')),None)
    current={'title':target.get('title') if target else '', 'text':target.get('text','')[:16000] if target else '', 'abstract':paper_abstract,'section_titles':[s['title'] for s in state['sections']]}
    if target and target.get('selected_passage'):
        from paragraph_selection import narrative_context
        current.update(text=target['selected_passage']['text'], narrative_context=narrative_context(target), scope='selected_passage')
    result=json_result(generate,instructions,{'task':goal,'section':section,'current_paper':current,'mode':mode,'rules':[{'author':m['author'],'text':m['text']} for m in memories],'candidate_papers':catalog,'examples':pool},PLAN_SCHEMA,'writing_strategy')
    if not 2<=len(result['options'])<=3:raise ValueError('需要2–3个可比较方案')
    pids={p['id'] for p in catalog};sources={e['source_id']:e for e in pool}
    for option in result['options']:
        if not option['paper_ids'] or len(option['paper_ids'])>3 or any(p not in pids for p in option['paper_ids']):raise ValueError('推荐论文不在已读范围')
        if not option['source_ids'] or any(s not in sources or sources[s]['paper_id'] not in option['paper_ids'] for s in option['source_ids']):raise ValueError('方案引用了未读取的范例')
        option['sources']=[{'source_id':sid,'paper':sources[sid]['paper'],'paper_id':sources[sid]['paper_id'],'page':sources[sid]['page']} for sid in option['source_ids']]
    if len(json.dumps(result,ensure_ascii=False))>18000:raise ValueError('写作方案过长，请缩小任务')
    result.update(section=section,section_id=target.get('id') if target else None,base_version=(target.get('versions') or [{}])[-1].get('id') if target else None,goal=goal,mode=mode,id=uuid.uuid4().hex)
    library.write(Path(folder)/'.agent/strategy-proposals'/f"{result['id']}.json",result)
    library.write(plan_path(folder,section).with_name(section+'-proposal.json'),result)
    return result

def adopt(folder,state,proposal_id,index):
    if not re.fullmatch('[a-f0-9]{32}',str(proposal_id)) or type(index) is not int:raise ValueError('方案标识无效')
    proposal=json.loads((Path(folder)/'.agent/strategy-proposals'/f'{proposal_id}.json').read_text())
    if not 0<=index<len(proposal['options']):raise ValueError('方案序号无效')
    target=next((s for s in state['sections'] if s['id']==proposal['section_id']),None)
    if not target or (target.get('versions') or [{}])[-1].get('id')!=proposal['base_version']:raise ValueError('当前章节已更新，请重新推荐方案')
    result={'status':'用户选定的写作计划，事实仍需核对','section_id':target['id'],'base_version':proposal['base_version'],'goal':proposal['goal'],'option':proposal['options'][index]}
    path=plan_path(folder,proposal['section'])
    if path.exists():library.write(Path(folder)/'.agent/strategy-history'/f'{uuid.uuid4().hex}.json',json.loads(path.read_text()))
    library.write(path,result);config=set_settings(folder,proposal['mode'],settings(folder).get('goal',''))
    config['section_types'][target['id']]=proposal['section'];library.write(Path(folder)/'writing-strategy.json',config)
    return result
