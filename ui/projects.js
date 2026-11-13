'use strict';
let projectItems=[],projectTrash=false,projectRenaming=null,projectManaging=false;
function updateProjectLabel(){$('project-current-name').textContent=project?.name||'Project';}
function rememberProject(id){try{if(id)localStorage.setItem('draft.lastProject',id);else localStorage.removeItem('draft.lastProject');}catch{}}
function preferredProjectId(){try{const id=localStorage.getItem('draft.lastProject');return Array.from($('project-picker').options).some(o=>o.value===id)?id:null;}catch{return null;}}
const projectLoadBefore=loadProject;
loadProject=async function(id){await projectLoadBefore(id);rememberProject(id);updateProjectLabel();};
const projectCreateBefore=createProject;
createProject=async function(){await projectCreateBefore();rememberProject(project.id);updateProjectLabel();};
const projectBusyBefore=setBusy;
setBusy=function(value){projectBusyBefore(value);$('manage-projects').disabled=value;};
function clearProject(){
  clearTimeout(inputTimer);if(pdf)URL.revokeObjectURL(pdf.url);pdf=null;project=null;sections=[];selectedSection=-1;revision=0;folder='';storageFailed=false;editorTarget=null;history=[];transcript=[];
  rememberProject(null);showPDF();renderSections();renderChat();updateProjectLabel();$('save-indicator').textContent='请选择或新建 Project';
}
function projectDate(value){const date=new Date(value);return Number.isNaN(date.getTime())?'未知时间':date.toLocaleString('zh-CN',{year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'});}
async function fetchProjects(){const result=await localAPI('/api/projects'+(projectTrash?'?trash=1':''));projectItems=result.items;renderProjectList();}
function projectButton(text,fn,kind=''){const b=document.createElement('button');b.textContent=text;b.className=kind;b.disabled=projectManaging;b.onclick=fn;return b;}
function renderProjectList(){
  const list=$('projects-list');list.replaceChildren();const query=$('projects-search').value.trim().toLocaleLowerCase();const items=projectItems.filter(p=>p.name.toLocaleLowerCase().includes(query));
  $('projects-active').setAttribute('aria-pressed',String(!projectTrash));$('projects-trash').setAttribute('aria-pressed',String(projectTrash));
  if(!items.length){const empty=document.createElement('p');empty.className='projects-empty';empty.textContent=query?'没有匹配的 Project':projectTrash?'回收站为空':'还没有 Project，点击左侧“新建 Project”开始。';list.append(empty);return;}
  for(const item of items){
    const row=document.createElement('article');row.className='project-row';const info=document.createElement('div');info.className='project-info';
    const title=document.createElement('strong');title.textContent=item.name;info.append(title);
    if(item.id===project?.id&&!projectTrash){const badge=document.createElement('span');badge.className='project-badge';badge.textContent='当前';info.append(badge);}
    const meta=document.createElement('small');meta.textContent=item.type+' · '+item.sections+' 个章节 · '+(projectTrash?'移入回收站 ':'修改于 ')+projectDate(projectTrash?item.deletedAt:item.updated);info.append(meta);
    const actions=document.createElement('div');actions.className='project-actions';
    if(projectRenaming===item.id){
      const input=document.createElement('input');input.value=item.name;input.maxLength=120;input.setAttribute('aria-label','Project 新名称');input.disabled=projectManaging;info.replaceChildren(input,meta);
      const save=()=>projectAction('rename',item,{name:input.value});input.onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();save();}};
      actions.append(projectButton('保存名称',save),projectButton('取消',()=>{projectRenaming=null;renderProjectList();}));
    }else if(projectTrash){actions.append(projectButton('恢复',()=>projectAction('restore',item)));}
    else{actions.append(projectButton(item.id===project?.id?'继续写作':'打开',()=>openManagedProject(item)),projectButton('打开 PDF 位置',()=>manageTask(async()=>{const result=await revealProjectPDF(item.id);$('projects-feedback').textContent='已打开 PDF 位置：'+result.path;})),projectButton('重命名',()=>{projectRenaming=item.id;renderProjectList();}),projectButton('移入回收站',()=>{if(confirm('将“'+item.name+'”移入回收站？论文、对话和版本会保留，可随时恢复。'))projectAction('trash',item);},'project-danger'));}
    row.append(info,actions);list.append(row);
  }
}
async function manageTask(fn){
  if(busy||loadingFile||projectManaging)return;projectManaging=true;setBusy(true);clearTimeout(inputTimer);
  for(const id of ['projects-close','projects-active','projects-trash','projects-refresh','projects-search'])$(id).disabled=true;
  renderProjectList();$('projects-feedback').textContent='正在处理…';
  try{await fn();}catch(e){$('projects-feedback').textContent=e.message;}
  finally{projectManaging=false;setBusy(false);for(const id of ['projects-close','projects-active','projects-trash','projects-refresh','projects-search'])$(id).disabled=false;renderProjectList();}
}
async function openManagedProject(item){await manageTask(async()=>{
  if(project&&!await persist())throw new Error('请先处理当前 Project 的保存问题。');
  await loadProject(item.id);$('projects-dialog').close();localStatus('已打开 Project：'+project.name);
});}
async function projectAction(action,item,extra={}){await manageTask(async()=>{
  if(project&&!await persist())throw new Error('请先处理当前 Project 的保存问题。');
  const current=item.id===project?.id;
  const result=await localAPI('/api/projects/'+action,{method:'POST',headers:{'Content-Type':'application/json','X-Draft-Project':'1'},body:JSON.stringify({id:item.id,revision:current?revision:item.revision,...extra})});
  if(action==='rename'&&current){project.name=result.name;revision=result.revision;project.revision=revision;updateProjectLabel();}
  if(action==='trash'&&current){clearProject();await refreshLibrary();const next=$('project-picker').options[1]?.value;if(next)await loadProject(next);}
  projectRenaming=null;await refreshLibrary();await fetchProjects();
  $('projects-feedback').textContent=action==='rename'?'名称已更新。':action==='trash'?'已移入回收站，可以随时恢复。':'Project 已恢复，请在“历史 Project”中打开。';
});}
$('manage-projects').onclick=async()=>{if(busy||loadingFile)return;projectTrash=false;projectRenaming=null;$('projects-search').value='';$('projects-feedback').textContent='';$('projects-dialog').showModal();await manageTask(async()=>{if(project&&!await persist())throw new Error('当前 Project 保存失败，请先处理。');await fetchProjects();$('projects-feedback').textContent='';});};
$('projects-close').onclick=()=>{if(!projectManaging)$('projects-dialog').close();};
$('projects-dialog').addEventListener('cancel',e=>{if(projectManaging)e.preventDefault();});
for(const [id,trash] of [['projects-active',false],['projects-trash',true]])$(id).onclick=async()=>{await manageTask(async()=>{projectTrash=trash;projectRenaming=null;await fetchProjects();$('projects-feedback').textContent='';});};
$('projects-refresh').onclick=()=>manageTask(async()=>{await fetchProjects();$('projects-feedback').textContent='列表已更新。';});
$('projects-search').oninput=renderProjectList;

async function revealProjectPDF(id){
  if(!id)throw new Error('请先打开 Project。');
  return localAPI('/api/projects/reveal-pdf',{method:'POST',headers:{'Content-Type':'application/json','X-Draft-Project':'1'},body:JSON.stringify({id})});
}
$('pdf-reveal').onclick=async()=>{
  const button=$('pdf-reveal');button.disabled=true;
  try{const result=await revealProjectPDF(project?.id);localStatus('已打开 PDF 位置：'+result.path);}
  catch(e){localStatus(e.message);}
  finally{button.disabled=false;}
};
