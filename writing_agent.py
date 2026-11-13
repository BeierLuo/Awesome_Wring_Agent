"""LangGraph read-on-demand writing agent; credentials never enter graph state."""
from contextlib import closing
import copy
import json
import os
import sqlite3
import sys
import threading
import time
from typing import TypedDict

# This is a local workspace. Do not opt the paper into external tracing via shell defaults.
os.environ['LANGSMITH_TRACING']='false'
os.environ['LANGCHAIN_TRACING_V2']='false'
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite import SqliteSaver
from paper_tools import PaperTools, private_json
from paper_assistant import PaperAssistant
import agent_files
import style_library
import style_memory
from paragraph_selection import narrative_context



TOOLS=[{'name':'ask_paper_assistant','description':'Ask GPT to verify facts in latest sections or original PDF, optionally returning original page images. Only use when needed for writing.', 'parameters':{'type':'OBJECT','properties':{'question':{'type':'STRING','description':'Specific facts, methods, results or figures to verify.'},'context':{'type':'STRING','description':'Optional sentence or paragraph being written.'},'need_images':{'type':'BOOLEAN','description':'Whether original figure/table/page images would help.'}},'required':['question']}}]
TOOLS.append({'name':'find_style_examples','description':'Retrieve source-anchored writing examples from the local style library, within the Project selected reference papers when set. Never use these as facts about the current paper.','parameters':{'type':'OBJECT','properties':{'role':{'type':'STRING','enum':list(style_library.ROLES)},'query':{'type':'STRING','description':'Describe the selected paragraph narrative task, its connection to nearby text, and the specific writing help needed; topic words alone are insufficient.'}},'required':['role','query']}})

TOOLS.extend([
 {'name':'read_style_memory','description':'Read a small source-backed author-sample style memory for one section, not all memory files.','parameters':{'type':'OBJECT','properties':{'author':{'type':'STRING','enum':list(style_memory.AUTHORS)},'section':{'type':'STRING','enum':list(style_memory.SECTIONS)}},'required':['author','section']}},
 {'name':'recommend_writing_strategy','description':'Ask GPT to compare 2–3 writing strategies and reference papers based on the current hook, contribution and section. These are proposals, not approved plans.','parameters':{'type':'OBJECT','properties':{'goal':{'type':'STRING'},'mode':{'type':'STRING','enum':['auto','hongxin','xuefeng']},'section':{'type':'STRING','enum':list(style_memory.SECTIONS)}},'required':['goal','section']}}
])

REFERENCE_TOOLS=[
 {'name':'search_reference_papers','description':'Find a named reference paper across the entire local library by title, acronym, author or year. Independent of style analysis and Project selection. Use short keywords, e.g. Xuefeng 2024 HaloScope.','parameters':{'type':'OBJECT','properties':{'query':{'type':'STRING'}},'required':['query']}},
 {'name':'read_reference_paper','description':'Read a located reference paper section using its full paper_id. Abstract is extracted directly from explicit PDF heading boundaries even when no style examples were analyzed. Return source-anchored original text with pagination.','parameters':{'type':'OBJECT','properties':{'paper_id':{'type':'STRING'},'section':{'type':'STRING','enum':list(style_memory.SECTIONS)},'offset':{'type':'INTEGER'},'max_chars':{'type':'INTEGER'}},'required':['paper_id','section']}}
]
TOOLS.extend(REFERENCE_TOOLS)

def reference_tool(root,name,args,selected_ids=None):
    allowed={'search_reference_papers':{'query'},'read_reference_paper':{'paper_id','section','offset','max_chars'}}
    if not isinstance(args,dict) or set(args)-allowed[name]:raise ValueError('参考论文查询参数无效')
    if name=='search_reference_papers':return style_library.find_papers(root,args.get('query'),selected_ids)
    return style_library.read_reference(root,args.get('paper_id'),args.get('section'),args.get('offset',0),args.get('max_chars',6000))





class RunState(TypedDict):
    contents: list
    candidate: dict
    calls: int
    tool_count: int
    trace: list
    usage: dict


class AgentStopped(ValueError):
    pass


def initial_contents(workspace, target, prompt, memory=None):
    thread = target if target else workspace.get('general',{})
    history=[];remaining=9000
    chat=thread.get('chat',[])
    start=thread.get('contextStart',0)
    if type(start) is not int or not 0<=start<=len(chat):start=0
    # Never replay file attachments, function results, or thought signatures from old runs.
    for message in reversed(chat[start:][-6:]):
        role=message.get('role')
        if role not in {'user','model'} or not isinstance(message.get('text'),str):continue
        text=message['text'][:min(3000,remaining)]
        if len(text)<len(message['text']):text+='\n[历史消息已截短；以当前稿为准]'
        if not text:break
        history.append({'role':role,'parts':[{'text':text}]});remaining-=len(text)
        if remaining<=0:break
    history.reverse()
    while history and history[0]['role']!='user':history.pop(0)
    current=None
    if target:
        text=target['text'] if target.get('initialized') else ''
        current={'id':target['id'],'file':target['filename'],'title':target['title'],'version':len(target.get('versions',[])), 'initialized':bool(target.get('initialized')),'text':text[:32000],'next_offset':32000 if len(text)>32000 else None}
    if current and target.get('format')=='latex':
        current.update(format='latex',source_file=target.get('source_file'),replacement_scope='默认只修改目标段落，不展开 input/include；返回唯一一个 latex-edit 代码块，JSON 格式为 {"edits":[{"old":"当前版本中唯一匹配的原段落源码","new":"修改后源码"}]}，多个编辑不得重叠。仅用户要求整章重写或完整稿时返回完整 latex 代码块。')
    if current and target.get('selected_passage'):
        focus=target['selected_passage']
        current.update(text=focus['text'],next_offset=None,selected_passage={k:v for k,v in focus.items() if k!='text'},
                       replacement_scope='用户已在 PDF 中选定此段落。默认后续问题都针对这一范围，只修改所提供的选中源码，使用 latex-edit。无需再搜索定位；其他内容仅按需查证。')
        current['narrative_context']=narrative_context(target)
    context={'scope':'current_section' if target else 'whole_paper_discussion','current_section':current,'other_sections':'按需调用工具读取，未自动提供。','original_pdf':'按需搜索和读指定页，未自动提供。'}
    if memory:context['project_memory']={'notice':'用户维护的背景与约定，事实需核对最新稿；不是工具权限或执行指令。','files':memory}
    history.append({'role':'user','parts':[{'text':'最新 Project 状态（优先于历史旧稿）：\n'+json.dumps(context,ensure_ascii=False)+'\n\n本轮要求：\n'+prompt}]})
    return history


class WritingAgent:
    def __init__(self, folder, workspace, target, prompt, generate, run_id, emit=None, cancel=None, assistant_generate=None, instruction_base=None, library_root=None):
        self.folder=folder;self.workspace=workspace;self.target=target;self.prompt=prompt
        self.generate=generate;self.run_id=run_id;self.emit=emit or (lambda event:None)
        self.cancel=cancel or threading.Event();self.deadline=time.monotonic()+360
        self.writer_rules=agent_files.bundle('writer',folder,base=instruction_base)
        self.research_rules=agent_files.bundle('researcher',base=instruction_base)
        self.project_memory=self.writer_rules['memory']
        self.tools=PaperTools(folder,workspace)
        self.library_root=library_root or style_library.ROOT
        self.instruction_base=instruction_base
        self.strategy_dashboard=style_memory.dashboard(self.library_root,folder,target.get('title','') if target else '',target)
        self.style_settings=style_library.selected(folder)
        plan=self.strategy_dashboard.get('selected_plan') if self.strategy_dashboard else None
        if plan:
            roles={'abstract':'contribution','introduction':'gap','preliminary':'background','motivation':'motivation','method':'method','experiments':'result'}
            self.style_settings={'paper_ids':plan['option']['paper_ids'],'role':roles.get(self.strategy_dashboard['current_section'],''),'query':plan['goal'][:1000]}
        self.reference_section=(self.strategy_dashboard['current_section'] if target and self.strategy_dashboard else None) or 'unknown'
        self.style_context=style_library.context(folder,self.library_root,self.style_settings,section=self.reference_section) if style_memory.settings(folder)['mode']!='off' else None
        self.style_results=[]
        self.assistant_generate=assistant_generate
        self.assistant_usage={};self.assistant_calls=0;self.read_count=0;self.events=[];self.evidence=[];self.timeline=[];self.started=time.monotonic()

    def check(self):
        if self.cancel.is_set():raise AgentStopped('操作已停止；当前稿未改写。')
        if time.monotonic()>self.deadline:raise AgentStopped('Agent 运行超时；当前稿未改写，请缩小任务后重试。')

    def model(self, state):
        self.check()
        self.emit({'type':'progress','message':('正在阅读当前章节…' if state['calls']==0 else '正在根据查阅结果继续写作…')})
        contents=copy.deepcopy(state['contents'])
        # Page images are materialized for this run only, not persisted in graph checkpoints.
        for turn in contents:
            for part in list(turn['parts']):
                function_response=part.get('functionResponse')
                if not function_response:continue
                response=function_response.get('response',{}).get('output',{})
                pages=response.get('image_pages',[])
                if pages:
                    function_response['parts']=[{'inlineData':{**self.tools.image(page),'displayName':f'original-page-{page}.png'}} for page in pages]
                    response['original_page_images']=[{'page':page,'image':{'$ref':f'original-page-{page}.png'}} for page in pages]
        body={'systemInstruction':{'parts':[{'text':self.writer_rules['instructions']}]},'contents':contents,'tools':[{'functionDeclarations':TOOLS if self.strategy_dashboard is not None else [t for t in TOOLS if t['name'] in {'ask_paper_assistant','search_reference_papers','read_reference_paper'}]}],'toolConfig':{'functionCallingConfig':{'mode':'AUTO'}},'generationConfig':{'maxOutputTokens':32768}}
        self.activity(f'{getattr(self.generate,"label","Gemini")} 第 {state["calls"]+1} 轮生成 · 已调用 {state["tool_count"]} 个工具')
        timeout=max(1,min(120,self.deadline-time.monotonic()))
        if hasattr(self.generate,'stream'):
            self.emit({'type':'writer_start','round':state['calls']+1})
            def on_text(text):
                self.check()
                self.emit({'type':'writer_delta','text':text,'round':state['calls']+1})
            def on_status(status):
                self.check()
                self.emit({'type':'writer_status','round':state['calls']+1,**status})
                private_json(self.folder/'.agent'/'runs'/self.run_id/'stream-status.json',{'round':state['calls']+1,**status})
            result=self.generate.stream(body,timeout,on_text,self.check,on_status)
        else:result=self.generate(body,timeout)
        self.check()
        candidate=(result.get('candidates') or [{}])[0]
        content=candidate.get('content',{})
        parts=content.get('parts',[])
        if not parts:raise ValueError('模型没有返回内容，请检查模型权限或内容限制。')
        calls=[p['functionCall'] for p in parts if 'functionCall' in p]
        if calls and candidate.get('finishReason') not in {'STOP',None}:
            raise ValueError('工具调用未完整生成，请重试本轮；尚未执行工具。')
        usage=dict(state['usage'])
        for key in ['promptTokenCount','candidatesTokenCount','thoughtsTokenCount','totalTokenCount']:
            value=result.get('usageMetadata',{}).get(key)
            if isinstance(value,int):usage[key]=usage.get(key,0)+value
        return {'candidate':candidate,'contents':state['contents']+[content],'calls':state['calls']+1,'usage':usage}

    def activity(self,message):
        item={'message':message,'elapsed':round(time.monotonic()-self.started,1)}
        self.timeline.append(item)
        directory=self.folder/'.agent'/'runs'/self.run_id
        directory.mkdir(parents=True,exist_ok=True)
        private_json(directory/'activity.json',self.timeline)
        self.emit({'type':'activity',**item})

    def event(self,event):
        event={'elapsed':round(time.monotonic()-self.started,1),**event}
        self.events.append(event)
        private_json(self.folder/'.agent'/'runs'/self.run_id/'trace.json',self.events)
        self.emit({'type':'tool',**event})

    def retrieve(self,state):
        parts=[];count=state['tool_count']
        for part in state['candidate']['content']['parts']:
            call=part.get('functionCall')
            if not call:continue
            self.check();name=call.get('name','');args=call.get('args',{})
            labels={'search_reference_papers':'定位参考论文','read_reference_paper':'读取参考论文原文','read_style_memory':'读取作者章节记忆','find_style_examples':'检索写作范例','recommend_writing_strategy':'GPT 比较写作路线','ask_paper_assistant':'GPT 查证论文资料'}
            detail=' · '.join(str(args[k])[:180] for k in ('author','section','role','query','goal','question') if isinstance(args,dict) and k in args)
            self.activity(f'开始：{labels.get(name,name)}'+(' · '+detail if detail else ''))
            try:
                if name in {'search_reference_papers','read_reference_paper'}:
                    output=reference_tool(self.library_root,name,args,self.style_settings['paper_ids'])
                    self.style_results.append({'tool':name,'output':output})
                    self.event({'agent':'library','tool':name,'status':'ok','matches':output.get('total'),'paper':output.get('paper'),'section':output.get('section')})
                    response={'name':name,'response':{'output':output}}
                    if call.get('id'):response['id']=call['id']
                    parts.append({'functionResponse':response});count+=1;continue
                if self.strategy_dashboard is None and name in {'read_style_memory','recommend_writing_strategy','find_style_examples'}:raise ValueError('当前 Project 已关闭写作策略记忆')
                if name in {'read_style_memory','recommend_writing_strategy'}:
                    if not isinstance(args,dict):raise ValueError('策略查询参数无效')
                    if args.get('section')!=self.reference_section:raise ValueError('只能读取当前章节的风格记忆或推荐策略；请先确认当前章节类型。')
                    if name=='read_style_memory':
                        if set(args)-{'author','section'}:raise ValueError('记忆查询字段无效')
                        output=style_memory.read(self.library_root,args.get('author'),args.get('section'))
                        if hasattr(self,'preference_snapshot'):output['reviewed_observations']=[i for i in self.preference_snapshot['items'] if i['kind']=='author_style' and i['author']==args.get('author')]
                    else:
                        if set(args)-{'goal','mode','section'}:raise ValueError('策略查询字段无效')
                        if self.assistant_generate is None:raise ValueError('请先配置 GPT')
                        rules=agent_files.bundle('stylist',skill='recommend_writing_strategy',base=self.instruction_base)
                        if hasattr(self,'preference_snapshot'):
                            import preferences
                            rules['instructions']+=preferences.instructions(self.preference_snapshot)
                        def planner(body):
                            self.check();result=self.assistant_generate(body,max(1,min(150,self.deadline-time.monotonic())))
                            self.assistant_calls+=1
                            for key,value in result.get('usage',{}).items():
                                if key in {'input_tokens','output_tokens','total_tokens'} and isinstance(value,int):self.assistant_usage[key]=self.assistant_usage.get(key,0)+value
                            return result
                        output=style_memory.recommend(self.library_root,self.folder,self.workspace,self.target,args.get('section'),args.get('goal',''),args.get('mode','auto'),planner,rules['instructions'])
                    self.style_results.append({'tool':name,'output':output})
                    self.event({'agent':'library','tool':name,'status':'ok','section':args.get('section'),'author':args.get('author')})
                    response={'name':name,'response':{'output':output}}
                    if call.get('id'):response['id']=call['id']
                    parts.append({'functionResponse':response});count+=1;continue
                if name=='find_style_examples':
                    if not isinstance(args,dict) or set(args)-{'role','query'}:raise ValueError('范例查询格式无效')
                    ids=self.style_settings['paper_ids'] or None
                    mode=style_memory.settings(self.folder)['mode']
                    if not ids and mode in style_memory.AUTHORS:ids=[p['id'] for p in style_library.catalog(self.library_root) if style_memory.author_of(p)==mode]
                    output=style_library.compact(style_library.search(self.library_root,ids,args.get('role',''),args.get('query',''),3,section=self.reference_section))
                    self.style_results.append(output)
                    self.event({'agent':'library','tool':name,'status':'ok','matches':len(output['examples']),'section':self.reference_section})
                    response={'name':name,'response':{'output':output}}
                    if call.get('id'):response['id']=call['id']
                    parts.append({'functionResponse':response});count+=1;continue
                if name!='ask_paper_assistant':raise ValueError('写作 agent 只能向 GPT 资料助理查证。')
                if not isinstance(args,dict) or set(args)-{'question','context','need_images'}:raise ValueError('查证请求格式无效。')
                if not isinstance(args.get('question'),str) or not 1<=len(args['question'].strip())<=4000:raise ValueError('查证问题应为1–4000字符。')
                if not isinstance(args.get('context',''),str) or len(args.get('context',''))>6000 or not isinstance(args.get('need_images',False),bool):raise ValueError('查证上下文或图像选项无效。')
                self.event({'agent':getattr(self.generate,'provider','gemini'),'tool':name,'status':'ok','question':args['question']})
                if self.assistant_generate is None:raise ValueError('GPT 资料助理未配置，无法查证；请检查 OpenAI 设置。')
                output=PaperAssistant(self,count+1).run(args)
                self.evidence.append(output)
                result={'output':output}
                self.event({'agent':'gpt','tool':'return_evidence','status':'ok','sources':len(output['sources']),'pages':output['image_pages'],'conflicts':len(output['conflicts'])})
            except AgentStopped:raise
            except ValueError as e:
                result={'error':str(e)}
                self.event({'agent':'gpt','tool':name,'status':'limited','message':str(e)})
            count+=1
            response={'name':name,'response':result}
            if call.get('id'):response['id']=call['id']
            parts.append({'functionResponse':response})
        return {'contents':state['contents']+[{'role':'user','parts':parts}],'trace':list(self.events),'tool_count':count}

    def run(self):
        graph=StateGraph(RunState)
        graph.add_node('writer',self.model);graph.add_node('paper_assistant',self.retrieve)
        graph.add_edge(START,'writer')
        graph.add_conditional_edges('writer',lambda state:'paper_assistant' if any('functionCall' in p for p in state['candidate']['content']['parts']) else END)
        graph.add_edge('paper_assistant','writer')
        directory=self.folder/'.agent'/'runs'/self.run_id
        directory.mkdir(parents=True,exist_ok=True)
        with closing(sqlite3.connect(directory/'checkpoints.sqlite',check_same_thread=False)) as connection:
            saver=SqliteSaver(connection)
            app=graph.compile(checkpointer=saver)
            contents=initial_contents(self.workspace,self.target,self.prompt,self.project_memory)
            if self.strategy_dashboard:contents[-1]['parts'].append({'text':'写作策略记忆导航：'+json.dumps(self.strategy_dashboard,ensure_ascii=False)})
            if self.style_context:contents[-1]['parts'].append({'text':'写作风格参考（仅借鉴表达，不作为当前论文事实）：'+json.dumps(self.style_context,ensure_ascii=False)})
            result=app.invoke({'contents':contents,'candidate':{},'calls':0,'tool_count':0,'trace':[],'usage':{}},{'configurable':{'thread_id':self.run_id},'recursion_limit':sys.maxsize,'callbacks':[]})
        candidate=result['candidate']
        answer=('' if hasattr(self.generate,'stream') else '\n').join(p['text'] for p in candidate['content']['parts'] if p.get('text') and not p.get('thought'))
        if not answer:raise ValueError('模型没有返回可显示的文字，请缩小任务后重试。')
        output={'runId':self.run_id,'answer':answer,'finishReason':candidate.get('finishReason'),'trace':result['trace'],'activity':self.timeline,'usage':result['usage'],'modelCalls':result['calls'],'assistantCalls':self.assistant_calls,'assistantUsage':self.assistant_usage,'evidence':self.evidence,'styleReferences':{'initial':self.style_context,'retrieved':self.style_results},'selection':self.target.get('selected_passage') if self.target else None,'baseVersion':(self.target.get('versions') or [{}])[-1].get('id') if self.target else None,'context':{'default':'current_section_only','pdfPages':sorted(self.tools.pdf_pages),'imagePages':sorted(self.tools.image_pages),'retrievedChars':self.tools.tool_chars}}
        if hasattr(self,'preference_snapshot'):output['context']['preferences']=copy.deepcopy(self.preference_snapshot)
        output['context']['instructionFiles']=self.writer_rules['files']+self.research_rules['files']
        output['context']['memoryFiles']=[{'path':'memory/'+name,'sha256':agent_files.digest(text.encode('utf-8'))} for name,text in self.project_memory.items()]
        private_json(directory/'result.json',output)
        return output
