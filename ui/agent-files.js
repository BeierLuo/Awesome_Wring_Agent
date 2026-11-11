'use strict';
let agentDocuments=[],agentDocument=null,agentDocumentKind='memory',agentDocumentProject=null,agentDocumentWorking=false;
function agentFileDirty(){return agentDocument&&$('agent-file-text').value!==agentDocument.text;}
function agentFileQuery(extra={}){return new URLSearchParams({...agentDocumentProject?{workspaceId:agentDocumentProject}:{},...extra});}
async function agentFileAPI(path,options={}){return localAPI('/api/agent-files'+path,{...options,headers:{'Content-Type':'application/json','X-Draft-Instructions':'1',...options.headers}});}
function agentFileWorking(value){agentDocumentWorking=value;for(const id of ['agent-files-close','agent-file-picker','agent-file-save','agent-file-reload','agent-file-text','agent-tab-role','agent-tab-skill','agent-tab-memory'])$(id).disabled=value;$('agent-tab-memory').disabled=value||!agentDocumentProject;}
function agentFileCount(){$('agent-file-count').textContent=agentDocument?$('agent-file-text').value.length+' / '+agentDocument.limit+' 字符':'';$('agent-file-save').disabled=agentDocumentWorking||!agentDocument||!agentFileDirty();}
function agentFileDisplay(data){
  agentDocument=data;$('agent-file-text').value=data.text;$('agent-file-text').maxLength=data.limit;
  $('agent-file-path').textContent=data.path;
  $('agent-file-scope').textContent=data.scope==='project'?'仅当前 Project：'+(project?.name||'')+' · 每轮作为简短背景读取':'全局规则 · 对所有 Project 生效';
  $('agent-file-status').textContent=data.exists?'已从文件载入。保存后下一轮生效，正在运行的请求保持原有规则。':'文件缺失，请填写后保存。';agentFileCount();
}
async function agentFileLoad(key){const data=await agentFileAPI('/file?'+agentFileQuery({key}));agentFileDisplay(data);}
async function agentFileSwitchKind(kind){
  if(agentDocumentWorking)return;if(agentFileDirty()&&!confirm('放弃尚未保存的规则或记忆修改？'))return;
  agentFileWorking(true);
  try{agentDocumentKind=kind;agentDocument=null;for(const tab of ['role','skill','memory'])$('agent-tab-'+tab).setAttribute('aria-pressed',String(tab===kind));
    const items=agentDocuments.filter(d=>d.kind===kind);$('agent-file-picker').replaceChildren(...items.map(d=>new Option(d.title,d.key)));
    if(!items.length)throw new Error('请先选择 Project，再管理论文记忆。');$('agent-file-picker').value=items[0].key;await agentFileLoad(items[0].key);
  }catch(e){$('agent-file-status').textContent=e.message;}finally{agentFileWorking(false);agentFileCount();}
}
$('agent-files-open').onclick=async()=>{
  if(busy||loadingFile)return;agentDocumentProject=project?.id||null;agentDocument=null;agentFileWorking(true);$('agent-files-dialog').showModal();$('agent-file-status').textContent='正在读取文件…';
  try{agentDocuments=(await agentFileAPI('?'+agentFileQuery())).items;agentFileWorking(false);await agentFileSwitchKind(agentDocumentProject?'memory':'role');}
  catch(e){$('agent-file-status').textContent=e.message;agentFileWorking(false);}
};
for(const kind of ['role','skill','memory'])$('agent-tab-'+kind).onclick=()=>agentFileSwitchKind(kind);
$('agent-file-picker').onchange=async()=>{
  const key=$('agent-file-picker').value;
  if(agentFileDirty()&&!confirm('放弃尚未保存的修改？')){$('agent-file-picker').value=agentDocument.key;return;}
  agentFileWorking(true);try{await agentFileLoad(key);}catch(e){$('agent-file-status').textContent=e.message;$('agent-file-picker').value=agentDocument?.key||'';}finally{agentFileWorking(false);agentFileCount();}
};
$('agent-file-text').addEventListener('input',agentFileCount);
$('agent-file-save').onclick=async()=>{
  if(!agentDocument||agentDocumentWorking)return;const key=agentDocument.key,text=$('agent-file-text').value,sha256=agentDocument.sha256;agentFileWorking(true);
  try{const data=await agentFileAPI('/save',{method:'POST',body:JSON.stringify({key,text,sha256,...agentDocumentProject?{workspaceId:agentDocumentProject}:{}})});agentFileDisplay(data);$('agent-file-status').textContent='已保存到文件，下一轮生效。旧版本已保留。';}
  catch(e){$('agent-file-status').textContent=e.message;}finally{agentFileWorking(false);agentFileCount();}
};
$('agent-file-reload').onclick=async()=>{if(!agentDocument||agentDocumentWorking)return;if(agentFileDirty()&&!confirm('放弃当前编辑，重新读取磁盘上的文件？'))return;agentFileWorking(true);try{await agentFileLoad(agentDocument.key);}catch(e){$('agent-file-status').textContent=e.message;}finally{agentFileWorking(false);agentFileCount();}};
function closeAgentFiles(){if(agentDocumentWorking)return;if(agentFileDirty()&&!confirm('放弃尚未保存的修改？'))return;$('agent-files-dialog').close();agentDocument=null;}
$('agent-files-close').onclick=closeAgentFiles;$('agent-files-dialog').addEventListener('cancel',e=>{e.preventDefault();closeAgentFiles();});
const busyBeforeAgentFiles=setBusy;setBusy=function(value){busyBeforeAgentFiles(value);$('agent-files-open').disabled=value;};
window.addEventListener('beforeunload',e=>{if(agentFileDirty()){e.preventDefault();e.returnValue='';}});
