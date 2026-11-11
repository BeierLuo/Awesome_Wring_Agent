'use strict';
const gcpFields={gcp_auth:'gcp-auth',gcp_key:'gcp-key',gcp_project:'gcp-project',gcp_location:'gcp-location',gcp_model:'gcp-model'};
function gcpConfig(){return Object.fromEntries(Object.entries(gcpFields).map(([key,id])=>[key,$(id).value.trim()]));}
function updateProviderUI(){
  const cloud=$('writer-provider').value!=='gemini',mode=$('gcp-auth').value;
  $('gcp-settings').hidden=!cloud;$('gemini-settings').hidden=cloud;
  $('gcp-key-row').hidden=mode==='adc';$('gcp-project-row').hidden=mode==='express';$('gcp-adc-help').hidden=mode!=='adc';
  $('writer-status').textContent=cloud?'GCP · '+($('gcp-model').value||'gemini-4-argon'):'Gemini API · '+($('model').value.replace('models/','')||'请选择模型');
}
function writerConfig(){
  if(typeof settingsLoading!=='undefined'&&(settingsLoading||!settingsLoaded))throw new Error('正在恢复 API 配置，请稍等。');
  const provider=$('writer-provider').value||'gcp';
  if(provider==='gemini'){
    const key=$('key').value.trim(),model=$('model').value;
    if(!key||!model)throw new Error('请在备用选项中填写 Gemini Key 并选择模型。');
    return {provider,key,model};
  }
  const config=gcpConfig();
  if(config.gcp_auth!=='adc'&&!config.gcp_key)throw new Error('请先在 API 设置中填写 GCP Key，也可以切换为 Gemini API 备用。');
  if(config.gcp_auth!=='express'&&!config.gcp_project)throw new Error('请填写 GCP 项目 ID。');
  return {provider:'gcp',model:config.gcp_model||'gemini-4-argon',config};
}
async function gcpAPI(path,payload,signal){
  const response=await fetch('/api/gcp/'+path,{method:'POST',headers:{'Content-Type':'application/json','X-Draft-GCP':'1'},body:JSON.stringify(payload),signal});
  let data;try{data=await response.json();}catch{throw new Error('本地 GCP 服务未响应，请重新启动 Draft。');}
  if(!response.ok)throw new Error((data.error||'GCP 请求失败')+' 可在 API 设置中切换 Gemini API 备用。');
  return data;
}
const agentActivityByThread=new Map();
function agentActivityKey(){return (project?.id||'')+':'+(selected()?.id||'general');}
function parkAgentActivity(){
  $('agent-parking').append($('agent-activity'),$('agent-output'));
}
function mountAgentTurn(lines){
  parkAgentActivity();document.querySelectorAll('.agent-pending,.agent-pending-user').forEach(e=>e.remove());
  if(lines.prompt)renderEntry({role:'user',text:lines.prompt}).className+=' agent-pending-user';
  const article=document.createElement('article');article.className='message model agent-pending';
  const label=document.createElement('div');label.className='who';label.textContent='Gemini · '+(lines.completion||'正在回复');
  article.append(label,$('agent-activity'),$('agent-output'));$('messages').append(article);
  $('welcome').hidden=true;
  return article;
}
function restoreAgentActivity(){
  const lines=agentActivityByThread.get(agentActivityKey());
  $('agent-activity').hidden=!lines?.length;
  if(lines?.length)$('agent-events').textContent=lines.join('\n');
  $('agent-live').hidden=!lines?.completion;$('agent-live').textContent=lines?.completion||'';
  $('agent-output').hidden=!lines?.preview;$('agent-output-text').textContent=lines?.preview||'';
  if(lines&&!lines.success)mountAgentTurn(lines);
}
function traceLabel(event){
  const prefix=event.agent==='gpt'?'GPT · ':event.agent==='gemini'?'Gemini · ':'';
  return (event.status==='ok'?'✓ ':'⚠ ')+prefix+(event.tool?'['+event.tool+'] ':'')+traceDetail(event)+(Number.isFinite(event.elapsed)?' · '+event.elapsed+'s':'');
}
function traceDetail(event){
  if(event.status!=='ok')return (event.tool||'读取')+'：'+(event.message||'未完成');
  if(event.tool==='read_style_memory')return '读取 '+(event.author?event.author+' · ':'')+event.section+' 章节风格记忆';
  if(event.tool==='recommend_writing_strategy')return 'GPT 比较 '+event.section+' 写作路线';
  if(event.tool==='find_style_examples')return '论文库：读取 '+event.matches+' 个写作范例';
  if(event.tool==='ask_paper_assistant')return '请求查证：'+event.question;
  if(event.tool==='return_evidence')return '返回 '+event.sources+' 份来源'+(event.pages?.length?' · 原始图像第 '+event.pages.join('、')+' 页':'')+(event.conflicts?' · '+event.conflicts+' 处冲突':'');
  if(event.tool==='read_section')return event.initialized===false?'章节尚未提取，需查原始 PDF':'读取 '+event.source+' · v'+event.version;
  if(event.tool==='read_pdf_pages')return '查看'+(event.source==='compiled_pdf'?'编译':'原始')+' PDF 第 '+event.pages.join('、')+' 页'+(event.mode==='image'?'图像':'文字');
  if(event.tool==='search_paper')return '搜索资料 · 找到 '+event.matches+' 处匹配';
  return '查看章节目录 · '+event.sections+' 个章节';
}
async function runWritingAgent(writer,prompt,signal){
  const runId=W.uid(),config=writer.provider==='gcp'?{...writer.config,writer_provider:'gcp'}:{writer_provider:'gemini',gemini_key:writer.key,gemini_model:writer.model};
  config.openai_key=$('openai-key').value.trim();config.openai_model=$('openai-model').value.trim();
  const headers={'Content-Type':'application/json','X-Draft-Agent':'1'};
  const cancel=()=>{fetch('/api/agent/cancel',{method:'POST',headers,body:JSON.stringify({runId}),keepalive:true}).catch(()=>{});};
  signal.addEventListener('abort',cancel,{once:true});
  $('agent-activity').hidden=false;$('agent-activity').open=true;$('agent-events').textContent='默认只读取当前章节，尚未查阅其他资料。';
  const events=[];events.prompt=prompt;agentActivityByThread.set(agentActivityKey(),events);let result=null;
  mountAgentTurn(events).scrollIntoView({block:'end',behavior:'smooth'});
  const started=Date.now();let stepStarted=started,lastEvent=started,phase='正在连接本地 Agent',timer,preview='';
  $('agent-output').hidden=true;$('agent-output-text').textContent='';
  const tick=()=>{
    const now=Date.now(),quiet=Math.floor((now-lastEvent)/1000);
    $('agent-live').hidden=false;
    $('agent-live').textContent=phase+' · 本步骤 '+Math.floor((now-stepStarted)/1000)+'s · 总计 '+Math.floor((now-started)/1000)+'s'+(quiet>=15?' · '+quiet+'s 未收到新输出，仍在等待服务响应':'');
    timer=setTimeout(tick,1000);
  };tick();
  try{
    const response=await fetch('/api/agent/run' ,{method:'POST',headers,signal,body:JSON.stringify({runId,config,workspaceId:project.id,revision,sectionId:selected()?.id||null,prompt})});
    if(!response.ok){let error;try{error=await response.json();}catch{}throw new Error(error?.error||'本地 Agent 未响应，请重新启动 Draft。');}
    const handle=event=>{
      lastEvent=Date.now();
      if(event.type==='writer_start'){preview='';events.preview='';$('agent-output-text').textContent='';$('agent-output').hidden=true;}
      if(event.type==='writer_delta'){preview+=event.text;events.preview=preview;$('agent-output').hidden=false;$('agent-output-text').textContent=preview;phase='Gemini 正在输出回复';}

      if(event.type==='error'){events.push('⚠ '+event.error);$('agent-events').textContent=events.join('\n');throw new Error(event.error);}
      if(event.type==='progress')status(event.message);
      if(event.type==='activity'){phase=event.message;stepStarted=Date.now();events.push('→ '+event.message+' · 开始于 '+event.elapsed+'s');$('agent-events').textContent=events.join('\n');status(event.message);}
      if(event.type==='tool'){events.push(traceLabel(event));$('agent-events').textContent=events.join('\n');status(events.at(-1));}
      if(event.type==='result')result=event;
    };
    const reader=response.body.getReader(),decoder=new TextDecoder();let buffer='';
    try{while(true){const {value,done}=await reader.read();if(done)break;buffer+=decoder.decode(value,{stream:true});let newline;while((newline=buffer.indexOf('\n'))>=0){const line=buffer.slice(0,newline);buffer=buffer.slice(newline+1);if(line.trim())handle(JSON.parse(line));}}buffer+=decoder.decode();if(buffer.trim())handle(JSON.parse(buffer));}
    finally{reader.releaseLock();}
    if(!result)throw new Error('Agent 连接中断，输入已保留，请重试。');
    if(!events.length)$('agent-events').textContent='本轮仅使用当前章节和必要对话，没有读取其他章节或 PDF。';
    if(pdf)$('filesize').textContent=(pdf.blob.size/1024/1024).toFixed(2)+' MB · 本地资料，按需读页';
    return result;
  }catch(error){events.push(signal.aborted?'已停止，当前稿未改写。':'运行未完成：'+error.message);$('agent-events').textContent=events.join('\n');throw error;}finally{clearTimeout(timer);$('agent-live').textContent=(result?'本轮已完成':signal.aborted?'本轮已停止':'本轮未完成')+' · 总计 '+Math.floor((Date.now()-started)/1000)+'s';events.completion=$('agent-live').textContent;if(result){events.success=true;$('agent-output').hidden=true;events.preview='';}signal.removeEventListener('abort',cancel);}
}
['writer-provider','gcp-auth','model'].forEach(id=>$(id).addEventListener('change',updateProviderUI));
$('gcp-model').addEventListener('input',updateProviderUI);
$('test-gcp').onclick=async()=>{
  const button=$('test-gcp');button.disabled=true;$('gcp-connection').textContent='正在测试 GCP 模型访问…';
  try{const data=await gcpAPI('test',{config:gcpConfig()},AbortSignal.timeout(210000));$('gcp-connection').textContent='连接成功 · '+data.model+'。点击“保存配置”后开始写作。';}
  catch(e){$('gcp-connection').textContent=e.name==='TimeoutError'?'测试超时，请检查网络后重试。':e.message;}
  finally{button.disabled=false;}
};
