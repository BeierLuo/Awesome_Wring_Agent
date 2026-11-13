'use strict';
const W=WorkspaceCore;
let project=null, revision=0, folder='', saveQueue=Promise.resolve(), storageFailed=false, editorTarget=null;
const localStatus=t=>status(t);
const active=()=>selectedSection>=0?sections[selectedSection]:project?.general;
const selected=()=>selectedSection>=0?sections[selectedSection]:null;
const blankGeneral=()=>({chat:[],input:''});
async function localAPI(path,options){const r=await fetch(path,options);let data;try{data=await r.json();}catch{throw new Error('Project服务未启动，请使用启动文件打开网页。');}if(!r.ok)throw new Error(data.error||'本地文件操作失败');return data;}
function snapshot(){if(!project)return null;return {format:'paper-local-v1',id:project.id,name:project.name,revision,created:project.created,updated:new Date().toISOString(),sections:W.copy(sections),general:W.copy(project.general),selected:selectedSection,pdfName:pdf?.name||project.pdfName||'',...(project.latex?{latex:W.copy(project.latex)}:{})};}
function persist(includePDF=false){if(!project)return Promise.resolve(true);let state=snapshot();const data=includePDF?pdf?.data:null;
  $('save-indicator').textContent='正在保存到本地…';
  const job=saveQueue.then(async()=>{if(project?.latex)state=snapshot();state.revision=revision;const result=await localAPI('/api/save',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({state,pdfData:data})});revision=result.revision;folder=result.folder;if(result.state&&typeof reconcileLatexState==='function')reconcileLatexState(result.state);storageFailed=false;$('save-indicator').textContent='已保存到本地文件夹';$('folder-path').textContent=folder;return true;});
  saveQueue=job.catch(e=>{storageFailed=true;$('save-indicator').textContent='保存失败 · 请先导出备份';localStatus(e.message);return false;});return saveQueue;
}
async function refreshLibrary(){const result=await localAPI('/api/workspaces');$('project-picker').replaceChildren(new Option('选择 Project',''),...result.items.map(p=>new Option(p.name,p.id)));$('project-picker').value=project?.id||'';if(!project)$('folder-path').textContent='Project 文件夹：'+result.root;if(typeof updateProjectLabel==='function')updateProjectLabel();}
function bindProject(state){project=state;revision=state.revision||0;sections=state.sections;selectedSection=Number.isInteger(state.selected)&&state.selected>=0&&state.selected<sections.length?state.selected:-1;project.general=state.general||blankGeneral();history=[];transcript=[];}
function blobFromBase64(data){const bytes=Uint8Array.from(atob(data),c=>c.charCodeAt(0));return new Blob([bytes],{type:'application/pdf'});}
function showPDF(){const exists=!!pdf;$('document').hidden=!exists;$('drop').hidden=exists;$('split').disabled=!exists||busy;$('remove').hidden=true;if(pdf){$('filename').textContent=pdf.name;$('filesize').textContent=(pdf.blob.size/1024/1024).toFixed(2)+' MB · 本地原始 PDF';$('preview').href=pdf.url;}else $('preview').removeAttribute('href');if(typeof renderLatexProject==='function')renderLatexProject();}
async function loadProject(id){const result=await localAPI('/api/workspaces/'+encodeURIComponent(id));if(pdf)URL.revokeObjectURL(pdf.url);bindProject(result.state);pdf=result.pdfData?{name:project.pdfName,data:result.pdfData,blob:blobFromBase64(result.pdfData),remote:null}:null;if(pdf)pdf.url=URL.createObjectURL(pdf.blob);folder=result.folder;storageFailed=false;showPDF();renderSections();renderChat({latest:true});$('folder-path').textContent=folder;$('save-indicator').textContent='已从本地文件夹载入';updateImportStatus();await refreshLibrary();}
async function createProject(){const id=W.uid();bindProject({format:'paper-local-v1',id,name:'Untitled Project',created:new Date().toISOString(),revision:0,sections:[],general:blankGeneral(),selected:-1,pdfName:''});if(pdf)URL.revokeObjectURL(pdf.url);pdf=null;showPDF();renderSections();renderChat();await persist();await refreshLibrary();}
const previousSetBusy=setBusy;
setBusy=function(value){previousSetBusy(value);['prompt','new-conversation','conversation-picker','project-picker','new','reload-project','import-backup','prepare-section','draft-edit','versions-button','download-section','review-pending','save-section','accept-proposal','discard-proposal'].forEach(id=>$(id).disabled=value);if(!value)renderChat();else document.querySelectorAll('.adopt-button').forEach(b=>b.disabled=true);};
let renderedChatKey=null;
function renderChat({latest=false}={}){
  const messages=$('messages'),key=JSON.stringify([project?.id,selected()?.id||'general',active()?.conversationId,W.conversationStart(active())]);
  const position=!latest&&key===renderedChatKey?(messages.scrollTop||0):null;
  parkAgentActivity();document.querySelectorAll('.message').forEach(e=>e.remove());
  renderConversationPicker();
  const chat=W.currentChat(active());$('new-conversation').disabled=busy||!project;$('welcome').hidden=!!chat.length;
  for(const entry of chat)renderEntry(entry);
  restoreAgentActivity();$('prompt').value=active()?.input||'';
  // Open conversations at the latest message; preserve history reading on ordinary redraws.
  const top=position??messages.scrollHeight;
  if(messages.scrollTo)messages.scrollTo({top,behavior:'instant'});else messages.scrollTop=top;
  renderedChatKey=key;
}
function renderEntry(entry){const el=document.createElement('article');el.className='message '+(entry.role==='user'?'user':'model');const label=document.createElement('div');label.className='who';label.textContent=entry.role==='user'?'你':(entry.provider==='openai'?'OpenAI · ':entry.provider==='gcp'?'GCP · ':'GEMINI API · ')+(entry.model?.replace('models/','')||'修改建议');const body=document.createElement('div');body.className='body';DraftMarkdown.mount(body,entry.text);el.append(label);if(entry.agent?.styleReferences?.initial?.papers?.length){const refs=document.createElement('p');refs.className='reading-trace';refs.textContent='写作参考：'+entry.agent.styleReferences.initial.papers.map(p=>p.name).join('、');el.append(refs);}if(entry.agent){const details=document.createElement('details');details.className='reading-trace';details.open=true;const summary=document.createElement('summary');const trace=entry.agent.trace||[];const skills=[...new Set(trace.filter(e=>e.tool&&e.tool!=='return_evidence').map(e=>e.tool))];summary.textContent='Agent 执行过程 · '+(skills.length?'Skills: '+skills.join(' · '):'未调用工具');const pre=document.createElement('pre');pre.textContent=[...(entry.agent.activity||[]).map(e=>({elapsed:e.elapsed,text:'→ '+(window.DraftLanguage?.systemText(e.message)??e.message)})),...trace.map(e=>({elapsed:e.elapsed||0,text:traceLabel(e)}))].sort((a,b)=>a.elapsed-b.elapsed).map(e=>e.text).join('\n')||(entry.agent.styleReferences?.initial?'已提供所选论文的风格范例；没有发送整篇参考 PDF。':'没有读取其他章节或 PDF。');const tokens=entry.agent.usage?.promptTokenCount;if(Number.isFinite(tokens))pre.textContent+='\n写作模型累计输入：'+tokens+' tokens';const gptTokens=entry.agent.assistantUsage?.input_tokens;if(Number.isFinite(gptTokens))pre.textContent+='\nGPT 查证累计输入：'+gptTokens+' tokens · '+entry.agent.assistantCalls+' 次调用';details.append(summary,pre);el.append(details);}el.append(body);if(entry.role==='model'){const copy=document.createElement('button');copy.textContent='复制';copy.onclick=()=>navigator.clipboard.writeText(entry.text).catch(()=>localStatus('请选中文字手动复制。'));el.append(copy);if(selected()){const apply=document.createElement('button');apply.className='adopt-button';apply.textContent=selected().format==='latex'?'查看 LaTeX 修改稿':'交给 ChatGPT 整理写回';apply.disabled=busy||entry.canAdopt===false;if(entry.canAdopt===false)apply.textContent='回复未完成，请先继续';apply.onclick=()=>prepareProposal(entry);el.append(apply);if(selected().format==='latex'){const adopt=document.createElement('button');adopt.className='adopt-button';adopt.textContent='采用当前 LaTeX 修改稿';adopt.disabled=busy||entry.canAdopt===false;adopt.onclick=()=>adoptLatexRevision(entry);el.append(adopt);}}}$('messages').append(el);return el;}
renderSections=function(){const list=$('section-list');list.replaceChildren();[{title:'全文讨论'},...sections].forEach((s,i)=>{const b=document.createElement('button');b.className='section-item'+(selectedSection===i-1?' active':'');b.textContent=s.title+(i>0&&s.initialized?' · v'+s.versions.length:'');b.disabled=busy;b.onclick=async()=>{if(busy)return;if(active())active().input=$('prompt').value;selectedSection=i-1;renderSections();renderChat();await persist();localStatus(selected()?'当前文件：'+selected().filename:'全文讨论不会改写任何章节文件。');};list.append(b);});$('edit-section').hidden=selectedSection<0;$('export-sections').hidden=!!project?.latex||!sections.length;$('context').textContent=selected()?selected().filename+' · 独立对话':'全文讨论';updateImportStatus();renderDraft();};
function renderDraft(){const s=selected();$('draft-panel').hidden=!s;if(!s)return;$('draft-name').textContent=s.source_file||s.filename;$('draft-meta').textContent=s.initialized?'当前版本 v'+s.versions.length+' · '+s.text.length+' 字符':'待提取原稿 · PDF 第 '+s.start_page+'–'+s.end_page+' 页';$('prepare-section').hidden=s.initialized;renderSource($('draft-preview'),s.initialized?(s.text||'（本章节为空，可开始起草）'):'首次发送前将由 ChatGPT 提取并保存原文。');$('pending-bar').hidden=!s.pending;}
async function operation(label,fn,timeout=390000){if(busy)return;setBusy(true);controller=new AbortController();const timer=timeout?setTimeout(()=>controller.abort(),timeout):null;localStatus(label);try{return await fn(controller.signal);}catch(e){localStatus(e.name==='AbortError'?'操作已停止或超时；已保存的稿件与版本保留，未完成的提取可继续。':e.message);return null;}finally{clearTimeout(timer);controller=null;setBusy(false);}}
async function paperContext(options,signal){return localAPI('/api/paper/context',{method:'POST',headers:{'Content-Type':'application/json','X-Draft-Agent':'1'},signal,body:JSON.stringify({workspaceId:project.id,...options})});}
async function maintainRequest(task,text,schema,signal,extra=[]){
  const query=new URLSearchParams({workspaceId:project.id,task});
  const config=await localAPI('/api/agent-files/context?'+query,{headers:{'X-Draft-Instructions':'1'},signal});
  const content=[{type:'input_text',text},...extra,{type:'input_text',text:'Project 记忆（人工维护，提取原文时不得据此改写）：'+JSON.stringify(config.memory)}];
  const r=await fetch('https://api.openai.com/v1/responses',{method:'POST',headers:{Authorization:'Bearer '+$('openai-key').value.trim(),'Content-Type':'application/json'},signal:AbortSignal.any([signal,AbortSignal.timeout(180000)]),body:JSON.stringify({model:$('openai-model').value.trim(),store:false,max_output_tokens:16000,instructions:config.instructions,input:[{role:'user',content}],text:{format:{type:'json_schema',name:'section_document',strict:true,schema}}})});
  return parseStructured(await jsonResponse(r,'OpenAI'));
}

const draftSchema={type:'object',additionalProperties:false,properties:{text:{type:'string'},notes:{type:'string'}},required:['text','notes']};
async function extractDraft(s,signal){
  if(s.initialized)return;s.pending=null;
  const chunks=[],notes=[];
  for(let start=s.start_page;start<=s.end_page;start+=8){
    signal.throwIfAborted();
    const end=Math.min(start+7,s.end_page);localStatus('ChatGPT 正在提取 '+s.title+' · 第 '+start+'–'+end+' 页…');
    const pages=await paperContext({mode:'pages',start_page:start,end_page:end},signal);
    const extra=(pages.images||[]).flatMap(image=>[{type:'input_text',text:'以下是 PDF 物理第 '+image.page+' 页：'},{type:'input_image',image_url:'data:'+image.mimeType+';base64,'+image.data,detail:'high'}]);
    const result=await maintainRequest('extract_section',JSON.stringify({title:s.title,section_start:s.start_page,section_end:s.end_page,batch_start:start,batch_end:end,pages:pages.pages}),draftSchema,signal,extra);
    if(typeof result.text!=='string')throw new Error('提取结果缺少正文');chunks.push(result.text);if(result.notes)notes.push(result.notes);
  }
  signal.throwIfAborted();
  const text=chunks.filter(Boolean).join('\n\n');
  if(!text.trim())throw new Error('未提取到 '+s.title+' 的原文，请核对该节页码范围。');
  s.extractionNotes=notes.join('\n');
  W.commit(s,text,'ChatGPT 按页提取初始原稿');
  if(!await persist())throw new Error('原稿已提取，但本地保存失败。请导出备份后重试。');renderSections();localStatus(notes.join('\n')||'原稿已保存，请核对后继续发送。');
}
// The existing directory button now sends local heading candidates instead of PDF bytes.
openaiRequest=async function(instructions,prompt,schema,limit,signal){
  if(!project||!await persist())throw new Error('请先保存Project。');
  const outline=await paperContext({mode:'outline'},signal);
  if(outline.page_candidates.every(p=>p.needs_image))throw new Error('这是扫描版 PDF，尚无可搜索文字。请先为 PDF 添加 OCR 文字层，再识别章节。');
  const parsed=await maintainRequest('outline_sections',prompt+'\n'+JSON.stringify(outline),schema,signal);
  return {status:'completed',output:[{content:[{type:'output_text',text:JSON.stringify(parsed)}]}]};
};

async function prepareSection(){const s=selected();if(!s||!hasOpenai())return;await operation('ChatGPT 正在提取 '+s.title+'…',async signal=>{await extractDraft(s,signal);openEditor(s);});}
function openEditor(s){editorTarget=s;$('section-title').textContent=s.filename+' · v'+s.versions.length;$('section-text').value=s.text||'';setEditorPreview('section',false);$('section-dialog').showModal();}
$('prepare-section').onclick=prepareSection;$('draft-edit').onclick=()=>{const s=selected();if(s?.initialized)openEditor(s);else prepareSection();};$('edit-section').onclick=$('draft-edit').onclick;
function closeEditor(){if(editorTarget&&$('section-text').value!==editorTarget.text&&!confirm('放弃尚未保存的手动编辑？'))return;$('section-dialog').close();editorTarget=null;}
$('close-section').onclick=closeEditor;$('section-dialog').addEventListener('cancel',e=>{e.preventDefault();closeEditor();});
$('save-section').onclick=async()=>{if(!editorTarget||busy)return;W.commit(editorTarget,$('section-text').value,'手动编辑');if(await persist()){$('section-dialog').close();editorTarget=null;renderSections();localStatus('当前稿已保存为新版本。');}};
$('download-section').onclick=()=>{const s=selected();if(!s?.initialized){localStatus('请先提取或编辑原稿。');return;}download(s.text,s.filename);};
$('versions-button').onclick=()=>{const s=selected();if(!s?.versions.length){localStatus('还没有保存的版本。');return;}$('version-picker').replaceChildren(...s.versions.map((v,i)=>new Option('v'+(i+1)+' · '+new Date(v.at).toLocaleString()+' · '+v.reason,v.id)));$('version-picker').value=s.versions.at(-1).id;showVersion();$('versions-dialog').showModal();};
function showVersion(){const v=selected()?.versions.find(v=>v.id===$('version-picker').value);renderSource($('version-preview'),v?.text||'（空稿）');}
$('version-picker').onchange=showVersion;$('close-versions').onclick=()=>$('versions-dialog').close();
$('restore-version').onclick=async()=>{const s=selected(),v=s?.versions.find(v=>v.id===$('version-picker').value);if(!v||busy)return;W.commit(s,v.text,'恢复历史版本 '+v.id);s.pending=null;if(await persist()){$('versions-dialog').close();renderSections();localStatus('已恢复为当前稿，原有历史版本全部保留。');}};
async function adoptLatexRevision(entry){
  const s=selected();if(!s||s.format!=='latex'||busy||entry.canAdopt===false)return;
  await operation('正在采用 LaTeX 修改稿…',async()=>{
    const pending=W.latexRevision(s,entry);
    const previous={text:s.text,initialized:s.initialized,versions:W.copy(s.versions),pending:s.pending};
    s.pending=pending;W.accept(s);
    if(!await persist()){Object.assign(s,previous);renderSections();return;}
    renderSections();localStatus('已写入 '+(s.source_file||s.filename)+' · v'+s.versions.length+'。点击“编译 PDF”即可更新预览。');
  });
}
async function prepareProposal(entry){const s=selected();if(!s||busy||entry.canAdopt===false)return;if(s.format==='latex'){await operation('正在准备 LaTeX 修改稿…',async()=>{const pending=W.latexRevision(s,entry);if(s.pending&&!confirm('已有一份待确认稿，是否替换？'))return;s.pending=pending;if(!await persist())return;renderDraft();openProposal();});return;}if(!hasOpenai())return;if(s.pending&&!confirm('已有一份待确认稿，是否用新的整理结果替换？'))return;await operation('ChatGPT 正在把建议整理成完整章节稿…',async signal=>{if(!s.initialized)await extractDraft(s,signal);const result=await maintainRequest('apply_revision',JSON.stringify({file:s.filename,current_text:s.text,selected_gemini_response:entry.text,request:entry.request||'',response_based_on:entry.baseVersion,current_version:s.versions.at(-1)?.id}),draftSchema,signal);if(typeof result.text!=='string')throw new Error('未返回完整修改稿');s.pending={...W.proposal(s,result.text,entry.id),notes:result.notes};await persist();renderDraft();openProposal();});}
function openProposal(){const s=selected();if(!s?.pending)return;renderSource($('proposal-before'),s.text||'（空稿）');$('proposal-after').value=s.pending.text;$('proposal-note').textContent=s.filename+' · 确认后写入新版本。\n'+(s.pending.notes||'');setEditorPreview('proposal',false);$('proposal-dialog').showModal();}
$('review-pending').onclick=openProposal;$('close-proposal').onclick=async()=>{if(selected()?.pending)selected().pending.text=$('proposal-after').value;await persist();$('proposal-dialog').close();};
$('proposal-dialog').addEventListener('cancel',e=>{e.preventDefault();$('close-proposal').onclick();});
$('accept-proposal').onclick=async()=>{if(busy)return;const s=selected();if(!s?.pending)return;try{s.pending.text=$('proposal-after').value;W.accept(s);if(await persist()){$('proposal-dialog').close();renderSections();localStatus('已写入 '+s.filename+' · v'+s.versions.length+'。下一轮 写作 Agent 将读取这个版本。');}}catch(e){localStatus(e.message);$('proposal-note').textContent=e.message;}};
$('discard-proposal').onclick=async()=>{if(selected())selected().pending=null;await persist();$('proposal-dialog').close();renderDraft();};
$('form').onsubmit=async e=>{e.preventDefault();if(busy||loadingFile)return;clearTimeout(inputTimer);const request=$('prompt').value.trim();if(!request)return;if(!project)await createProject();let writer;try{writer=writerConfig();}catch(error){status(error.message);$('dialog').showModal();return;}const target=selected(),thread=active();thread.input=request;
  if(target&&!target.initialized){if(!hasOpenai())return;await operation('ChatGPT 正在准备章节原稿…',async signal=>{await extractDraft(target,signal);openEditor(target);localStatus('已提取并保存初始稿。请核对原文，再次点击发送即可交给 写作 Agent。');});return;}
  await operation('写作 Agent 正在阅读当前章节…',async signal=>{
    if(!await persist())throw new Error('请先解决本地保存问题，再继续写作。');
    const result=await runWritingAgent(writer,request,signal);
    thread.chat.push({id:W.uid(),role:'user',text:request,at:new Date().toISOString()},{id:W.uid(),role:'model',text:result.answer,provider:result.provider,model:result.model,reasoningEffort:result.reasoningEffort,request,canAdopt:result.finishReason==='STOP',baseVersion:result.baseVersion,selection:result.selection,agent:{runId:result.runId,trace:result.trace,activity:result.activity,usage:result.usage,context:result.context,modelCalls:result.modelCalls,assistantCalls:result.assistantCalls,assistantUsage:result.assistantUsage,evidence:result.evidence,styleReferences:result.styleReferences},at:new Date().toISOString()});
    thread.input='';await persist();renderChat();window.DraftPreferences?.afterTurn(result);$('messages').lastElementChild?.scrollIntoView({block:'end',behavior:'smooth'});
    localStatus(result.finishReason==='STOP'?(target?.format==='latex'?'回复已保存。可点击“采用当前 LaTeX 修改稿”直接保存，或点击“查看 LaTeX 修改稿”先核对。':'回复已保存。需要采用时点击“交给 ChatGPT 整理写回”。'):'回复可能未完成，请让 Agent 继续后再整理写回。');
  });};

function updateImportStatus(){
  if(project?.latex){$('split').hidden=true;$('split-status').textContent='已从源码载入 '+sections.length+' 个章节块';return;}$('split').hidden=false;
  const ready=sections.filter(s=>s.initialized).length,remaining=sections.length-ready;
  $('split').textContent=!sections.length?'识别并提取全部章节':remaining?'继续提取原文（'+remaining+'）':'原文已全部提取';
  $('split').disabled=busy||!pdf||!!sections.length&&!remaining;
  $('split-status').textContent=sections.length?'原文已就绪 '+ready+' / '+sections.length+' 个章节':'上传 PDF 后自动识别并提取全部章节';
}
const oldSplit=$('split').onclick;
async function prepareAllSections(){
  if(busy||loadingFile||!pdf)return;
  if(typeof settingsLoading!=='undefined'&&(settingsLoading||!settingsLoaded)){localStatus('API 配置尚未恢复，请稍后点击“识别并提取全部章节”。');return;}
  if(!hasOpenai())return;
  clearTimeout(inputTimer);
  if(!sections.length){
    await oldSplit();if(!sections.length)return;
    sections=sections.map(W.makeSection);project.sections=sections;
    if(!await persist())return;renderSections();renderChat();
  }
  if(sections.every(s=>s.initialized)){updateImportStatus();return;}
  await operation('正在准备全部章节原文…',async signal=>{
    for(const section of sections){
      signal.throwIfAborted();if(section.initialized)continue;
      const ready=sections.filter(s=>s.initialized).length;
      localStatus('正在提取 '+(ready+1)+' / '+sections.length+'：'+section.title+'…');
      try{await extractDraft(section,signal);}
      catch(error){
        if(signal.aborted)throw error;
        throw new Error('提取暂停在 '+section.title+'：'+error.message+' 已完成章节已保存，点击“继续提取原文”可接着处理。');
      }
      updateImportStatus();
    }
    localStatus('全部 '+sections.length+' 个章节原文已保存，可直接切换章节写作。请核对公式、跨页段落和章节边界。');
    return true;
  },0);
}
$('split').onclick=prepareAllSections;
const oldAttach=attach;
attach=async function(file){if(!file||busy||loadingFile)return;if(pdf||sections.length){localStatus('本Project已有论文或章节稿。请新建Project处理另一篇论文。');return;}if(!project)await createProject();await oldAttach(file);if(pdf){project.name=file.name.replace(/\.pdf$/i,'');project.pdfName=file.name;project.sections=sections;if(!await persist(true))return;await refreshLibrary();renderChat();updateImportStatus();await prepareAllSections();}};
$('new').onclick=async()=>{if(busy||loadingFile)return;clearTimeout(inputTimer);if(project&&!await persist())return;await createProject();localStatus('新Project已建立，旧论文仍保留在本地文件夹。');};
$('project-picker').onchange=async()=>{const id=$('project-picker').value;if(!id||id===project?.id)return;clearTimeout(inputTimer);if(project&&!await persist()){$('project-picker').value=project.id;return;}try{await loadProject(id);localStatus('已切换论文。');}catch(e){localStatus(e.message);}};
$('reload-project').onclick=async()=>{if(!project||busy)return;if(storageFailed&&!confirm('本地文件有新版本或保存失败。请先导出当前备份。确定从磁盘重新载入？'))return;try{await loadProject(project.id);localStatus('已重新读取本地文件，外部编辑已记录为新版本。');}catch(e){localStatus(e.message);}};
let inputTimer;$('prompt').addEventListener('input',()=>{if(active())active().input=$('prompt').value;clearTimeout(inputTimer);inputTimer=setTimeout(()=>persist(),500);});
function renderConversationPicker(){
  const picker=$('conversation-picker');
  const options=W.conversationHistory(active()).map((c,i)=>{
    const first=c.chat.find(m=>m.role==='user'&&m.text)?.text.replace(/\s+/g,' ').slice(0,32)||'空白会话';
    return new Option((c.current?'当前 · ':'历史 · ')+first,c.id);
  });
  picker.replaceChildren(...options);picker.value=options[0]?.value||'';picker.disabled=busy||options.length<2;
}
async function switchConversation(id=null){
  if(busy||loadingFile||!active())return;
  clearTimeout(inputTimer);
  const thread=active(),keys=['chat','input','contextStart','conversations','conversationId','conversationCreated'];
  const before=Object.fromEntries(keys.filter(k=>k in thread).map(k=>[k,W.copy(thread[k])]));
  setBusy(true);
  try{
    W.ensureConversations(thread);
    if(id==='legacy')id=thread.conversations[0]?.id;
    if(id==='current')id=thread.conversationId;
    W.changeConversation(thread,id);
    if(!await persist())throw new Error('会话切换未能保存，原会话已保留。');
    document.querySelectorAll('.agent-pending,.agent-pending-user').forEach(e=>e.remove());
    renderChat({latest:true});
    localStatus(id===null?'新会话已开始，旧对话可从历史会话列表切回。':'已切回历史会话，可继续聊天；写作仍以当前稿为准。');
  }catch(error){
    for(const key of keys){if(key in before)thread[key]=before[key];else delete thread[key];}
    localStatus(error.message);
  }finally{setBusy(false);$('prompt').focus();}
}
$('new-conversation').onclick=()=>switchConversation();
$('conversation-picker').onchange=()=>switchConversation($('conversation-picker').value);
$('export').onclick=()=>{const chat=[...(active()?.conversations||[]).flatMap(c=>c.chat),...(active()?.chat||[])];download('# '+(selected()?.title||'全文讨论')+'\n\n'+chat.map(m=>'## '+(m.role==='user'?'你':(m.provider==='openai'?'OpenAI':m.provider==='gcp'?'GCP':'Gemini API'))+'\n\n'+m.text).join('\n\n'),'章节对话.md');};
$('export-sections').onclick=()=>download(sections.map(s=>'# '+s.title+'\n\n'+(s.initialized?s.text:'[尚未提取；PDF 第 '+s.start_page+'–'+s.end_page+' 页]')).join('\n\n'),'论文当前稿.md');
$('backup').onclick=async()=>{if(!project){localStatus('请先打开Project。');return;}try{const data=await localAPI('/api/agent-files/memory?'+new URLSearchParams({workspaceId:project.id}),{headers:{'X-Draft-Instructions':'1'}});download(JSON.stringify({format:'paper-local-v1',state:snapshot(),pdfData:pdf?.data||null,memory:data.memory},null,2),(project.name||'论文')+'-完整备份.json');}catch(e){localStatus(e.message);}};
$('import-backup').onchange=async e=>{const file=e.target.files[0];if(!file||busy)return;try{if(file.size>60*1024*1024)throw new Error('备份文件过大');const data=JSON.parse(await file.text());if(data.format!=='paper-local-v1'||data.state?.format!=='paper-local-v1'||!Array.isArray(data.state.sections))throw new Error('不是有效的Project备份');if(project&&!await persist())return;data.state.id=W.uid();data.state.revision=0;data.state.name+='（导入）';const result=await localAPI('/api/save',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});await loadProject(data.state.id);localStatus('备份已导入为独立Project，原有文件未覆盖。');}catch(err){localStatus(err.message);}finally{e.target.value='';}};
window.addEventListener('beforeunload',e=>{if(busy||storageFailed){e.preventDefault();e.returnValue='';}});
(async()=>{try{await refreshLibrary();const first=(typeof preferredProjectId==='function'?preferredProjectId():null)||$('project-picker').options[1]?.value;if(first)await loadProject(first);}catch(e){localStatus(e.message);$('save-indicator').textContent='未连接Project服务';}})();

function setEditorPreview(kind,show){
  const input=$(kind==='section'?'section-text':'proposal-after'),preview=$(kind+'-rendered'),button=$(kind+'-preview-toggle');
  input.hidden=show;preview.hidden=!show;button.setAttribute('aria-pressed',String(show));
  button.textContent=show?'返回 Markdown 源码':(kind==='section'?'预览排版':'预览拟写入稿');
  if(project?.latex){button.textContent=show?'返回编辑':'查看源码';if(show){preview.replaceChildren();const pre=document.createElement('pre');pre.textContent=input.value;preview.append(pre);}}else if(show)DraftMarkdown.render(preview,input.value);
}
for(const kind of ['section','proposal'])$(kind+'-preview-toggle').onclick=()=>setEditorPreview(kind,$(kind+'-rendered').hidden);

function renderSource(element,text){if(project?.latex){element.replaceChildren();const pre=document.createElement('pre');pre.className='tex-source-preview';pre.textContent=text;element.append(pre);}else DraftMarkdown.mount(element,text);}
