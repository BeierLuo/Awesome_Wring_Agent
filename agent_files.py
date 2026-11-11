"""Explicit file-backed role rules, skill instructions, and per-project memory."""
import hashlib,json,os,uuid
from pathlib import Path

BASE=Path(__file__).resolve().parent
ROLE_SKILLS={'writer':['ask_paper_assistant','find_style_examples','read_style_memory'],'researcher':['list_sections','read_section','search_paper','read_pdf_pages'],'maintainer':['outline_sections','extract_section','apply_revision'],'stylist':['analyze_style','synthesize_style_memory','recommend_writing_strategy']}
ROLE_TITLES={'stylist':'GPT · 写作风格分析','writer':'Gemini · 写作规则','researcher':'GPT · 查证规则','maintainer':'GPT · 章节维护规则'}
SKILL_TITLES={'read_style_memory':'读取章节风格记忆','synthesize_style_memory':'归纳章节写作规则','recommend_writing_strategy':'推荐写作方案','find_style_examples':'查找写作范例','analyze_style':'分析参考论文风格','ask_paper_assistant':'请求 GPT 查证','list_sections':'章节目录','read_section':'读取最新章节','search_paper':'搜索证据','read_pdf_pages':'PDF 页面与图像','outline_sections':'识别目录','extract_section':'提取原文','apply_revision':'整理修改稿'}
MEMORY_DEFAULTS={'paper.md':'# 论文背景\n\n填写研究问题、论文目标和核心术语。具体事实请附章节或来源；不确定内容请标记待核对。\n','preferences.md':'# 写作偏好\n\n填写语言、语气、术语拼写、格式和应避免的表达。\n','decisions.md':'# 已确认约定\n\n记录你确认采用的重要写作决定，注明日期、适用章节和依据。未确认建议不要当成结论。\n'}
MEMORY_TITLES={'paper.md':'论文背景与术语','preferences.md':'写作偏好','decisions.md':'已确认约定'}
CATALOG={**{f'agents/{r}/AGENT.md':{'title':t,'kind':'role','limit':12000,'scope':'global'} for r,t in ROLE_TITLES.items()},**{f'skills/{k}/SKILL.md':{'title':t,'kind':'skill','limit':6000,'scope':'global'} for k,t in SKILL_TITLES.items()},**{f'memory/{k}':{'title':v,'kind':'memory','limit':2000,'scope':'project'} for k,v in MEMORY_TITLES.items()}}

def digest(raw):return hashlib.sha256(raw).hexdigest()
def safe_path(base,relative):
    base=Path(base);p=base/relative
    if base.is_symlink() or not p.resolve().is_relative_to(base.resolve()):raise ValueError('Agent 文件路径无效')
    current=p
    while current!=base:
        if current.is_symlink():raise ValueError('Agent 文件不支持符号链接')
        current=current.parent
    return p

def write(path,text):
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp');temp.write_text(text,encoding='utf-8');os.replace(temp,path)

def ensure_memory(folder):
    for name,text in MEMORY_DEFAULTS.items():
        path=safe_path(folder,'memory/'+name);path.parent.mkdir(parents=True,exist_ok=True)
        try:
            with path.open('x',encoding='utf-8') as file:file.write(text)
        except FileExistsError:pass

def validate_text(key,text):
    info=CATALOG[key]
    if not isinstance(text,str) or len(text)>info['limit'] or '\x00' in text:raise ValueError(f"{info['title']} 最多 {info['limit']} 字符，不能包含空字符")
    if info['scope']=='global' and not text.strip():raise ValueError('角色规则和技能说明不能为空')
    text.encode('utf-8')

def read_file(key,folder=None,base=None):
    if key not in CATALOG:raise ValueError('不支持的 Agent 文件')
    info=CATALOG[key]
    if info['scope']=='project':
        if folder is None:raise ValueError('请先选择 Project')
        ensure_memory(folder);root=folder
    else:root=base or BASE
    p=safe_path(root,key)
    if not p.exists():return {'key':key,**info,'text':'','sha256':None,'exists':False,'path':str(p)}
    if not p.is_file() or p.stat().st_size>info['limit']*4:raise ValueError('Agent 文件超出大小限制：'+key)
    raw=p.read_bytes();text=raw.decode('utf-8');validate_text(key,text)
    return {'key':key,**info,'text':text,'sha256':digest(raw),'exists':True,'path':str(p)}

def save_file(key,text,expected,folder=None,base=None):
    if key not in CATALOG:raise ValueError('不支持的 Agent 文件')
    validate_text(key,text);current=read_file(key,folder,base)
    if current['sha256']!=expected:raise ValueError('文件已被其他窗口或编辑器修改，请重新载入后再保存')
    if current['exists'] and text==current['text']:return current
    root=Path(folder if current['scope']=='project' else base or BASE)
    backup=('.agent/memory-history/' if current['scope']=='project' else '.local/agent-history/')+uuid.uuid4().hex+'/'+key
    if current['exists']:write(safe_path(root,backup),current['text'])
    write(safe_path(root,key),text)
    return read_file(key,folder,base)

def memory_snapshot(folder):
    return {name:read_file('memory/'+name,folder)['text'] for name in MEMORY_DEFAULTS}

def validate_memory(memory):
    if not isinstance(memory,dict) or set(memory)-set(MEMORY_DEFAULTS):raise ValueError('论文记忆备份字段无效')
    for name,text in memory.items():validate_text('memory/'+name,text)

def import_memory(folder,memory):
    validate_memory(memory);ensure_memory(folder)
    for name,text in memory.items():write(safe_path(folder,'memory/'+name),text)

def bundle(role,folder=None,skill=None,base=None):
    if role not in ROLE_SKILLS:raise ValueError('未知 Agent 角色')
    skills=ROLE_SKILLS[role]
    if skill is not None:
        if skill not in skills:raise ValueError('此角色不能使用指定技能')
        skills=[skill]
    keys=[f'agents/{role}/AGENT.md',*[f'skills/{s}/SKILL.md' for s in skills]]
    files=[read_file(key,base=base) for key in keys]
    for f in files:
        if not f['exists']:raise ValueError('缺少 Agent 文件，请在管理页补充：'+f['key'])
    return {'instructions':'\n\n'.join('【'+f['key']+'】\n'+f['text'] for f in files),
            'files':[{'path':f['key'],'sha256':f['sha256']} for f in files],
            'memory':memory_snapshot(folder) if folder else {}}
