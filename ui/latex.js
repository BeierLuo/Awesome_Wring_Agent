'use strict';
let latexOpenedFile=null,latexFileRevision=0,latexInfo=null,latexCompiling=false;
function latexQuery(extra={}){return new URLSearchParams({workspaceId:project.id,...extra}).toString();}
function latexRequest(action,payload={},signal){return localAPI('/api/latex/'+action,{method:'POST',headers:{'Content-Type':'application/json','X-Draft-LaTeX':'1'},body:JSON.stringify({workspaceId:project?.id,revision,...payload}),signal});}
function reconcileLatexState(state){
  const previous=new Map(sections.map(s=>[s.id,s]));const selectedId=selected()?.id;
  sections=state.sections.map(s=>{const existing=previous.get(s.id);if(!existing)return s;const input=existing.input;Object.assign(existing,s);existing.input=input;return existing;});
  project.latex=state.latex;project.sections=sections;revision=state.revision;
  selectedSection=sections.findIndex(s=>s.id===selectedId);project.selected=selectedSection;
  renderLatexProject();
}
function renderLatexProject(){
  const isLatex=!!project?.latex;$('latex-panel').hidden=!isLatex;
  $('backup').hidden=isLatex;$('backup').textContent='导出完整备份';$('export-sections').hidden=isLatex||!sections.length;
  $('download-section').textContent=isLatex?'↓ .tex':'↓ .md';
  if(!isLatex)return;
  $('drop').hidden=true;$('document').hidden=true;$('split').hidden=true;
  $('latex-summary').textContent=project.latex.files.length+' 个项目文件 · '+sections.length+' 个章节块 · 本地源码分节';
  const skipped=project.latex.skipped||[];$('latex-skipped').hidden=!skipped.length;$('latex-skipped-list').textContent=skipped.join('、')+'。原 ZIP 保留在本地 .latex/original.zip；源码导出只包含已载入文件。';
  $('latex-main').replaceChildren(...project.latex.mains.map(n=>new Option(n,n)));$('latex-main').value=project.latex.main;
  for(const id of ['latex-main','latex-files','latex-compile','latex-export'])$(id).disabled=busy||latexCompiling;
  if(latexInfo?.workspaceId!==project.id){latexInfo=null;$('latex-preview').hidden=true;$('latex-build-status').textContent='源码已就绪 · 尚未编译';$('latex-log').textContent='尚未编译。';}
  else showLatexBuild();
}
function showLatexBuild(){
  if(!project?.latex||!latexInfo)return;
  const compiled=latexInfo.compiled,stale=compiled&&compiled.sourceHash!==project.latex.sourceHash,last=latexInfo.lastBuild;
  $('latex-preview').hidden=!compiled;
  $('latex-build-status').textContent=latexCompiling?'正在本地编译…':last&&!last.ok?'最近一次编译失败'+(compiled?' · 保留上次成功的 PDF':'') :compiled?(stale?'源码已更新 · 请重新编译':'PDF 已更新 · '+new Date(compiled.at).toLocaleTimeString()):'源码已就绪 · 尚未编译';
  $('latex-log').textContent=[last?.error,last?.log].filter(Boolean).join('\n')||'尚未编译。';
  $('latex-pdf-note').textContent=stale?'这是上次成功编译的 PDF；源码已变化，请重新编译。':'这是本地源码编译的 PDF。';
}
async function refreshLatexInfo(){if(!project?.latex)return;const id=project.id;const info=await localAPI('/api/latex/info?'+latexQuery());if(project?.id!==id)return;latexInfo={...info,workspaceId:id};showLatexBuild();}
const beforeLatexLoad=loadProject;
loadProject=async function(id){await beforeLatexLoad(id);renderLatexProject();if(project.latex)await refreshLatexInfo();};
const beforeLatexBusy=setBusy;
setBusy=function(value){beforeLatexBusy(value);for(const id of ['project-picker','reload-project','latex-file-save','latex-file-picker'])$(id).disabled=value;if(project?.latex)renderLatexProject();};
const beforeLatexAttach=attach;
attach=async function(file){
  if(!file?.name.toLowerCase().endsWith('.zip'))return beforeLatexAttach(file);
  if(busy||loadingFile)return;if(file.size>40*1024*1024){localStatus('ZIP 最大支持40 MB。');return;}
  clearTimeout(inputTimer);if(project&&!await persist())return;
  loadingFile=true;setBusy(true);localStatus('正在本地导入 LaTeX 项目并准备章节…');
  try{
    const zipData=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result.split(',')[1]);reader.onerror=()=>reject(new Error('读取 ZIP 失败'));reader.readAsDataURL(file);});
    const result=await latexRequest('import',{name:file.name,zipData});
    await loadProject(result.state.id);await refreshLibrary();
    localStatus('LaTeX 项目已从源码本地分节，未调用 GPT 或读取 PDF。可直接编辑，或点击“编译 PDF”。');
  }catch(e){localStatus(e.message);}finally{loadingFile=false;$('file').value='';setBusy(false);}
};
$('latex-main').onchange=async()=>{
  const main=$('latex-main').value;
  await operation('正在切换主文档…',async()=>{clearTimeout(inputTimer);if(!await persist())return;await latexRequest('main',{main});await loadProject(project.id);localStatus('主文档已切换，章节已重新载入。');});
};
function fileDirty(){return latexOpenedFile&&$('latex-source').value!==latexOpenedFile.text;}
async function openLatexFile(path){
  const data=await localAPI('/api/latex/file?'+latexQuery({path}));latexOpenedFile=data;latexFileRevision=data.revision;
  $('latex-source').value=data.text;$('latex-source').hidden=false;$('latex-file-save').disabled=false;
  $('latex-file-meta').textContent=path;$('latex-file-status').textContent='本地源文件 · UTF-8';
}
$('latex-files').onclick=async()=>{if(busy||!project?.latex)return;clearTimeout(inputTimer);if(!await persist())return;
  try{$('latex-file-picker').replaceChildren(...project.latex.files.map(f=>{const o=new Option(f.path+(f.editable?'':' · 资源文件'),f.path);o.disabled=!f.editable||f.size>2*1024*1024;return o;}));
    const path=selected()?.source_file||project.latex.main;$('latex-file-picker').value=path;await openLatexFile(path);$('latex-file-dialog').showModal();
  }catch(e){localStatus(e.message);}
};
$('latex-file-picker').onchange=async()=>{if(fileDirty()&&!confirm('放弃尚未保存的源文件编辑？')){$('latex-file-picker').value=latexOpenedFile.path;return;}try{await openLatexFile($('latex-file-picker').value);}catch(e){$('latex-file-status').textContent=e.message;}};
function closeLatexFile(){if(fileDirty()&&!confirm('放弃尚未保存的源文件编辑？'))return;$('latex-file-dialog').close();latexOpenedFile=null;}
$('latex-file-close').onclick=closeLatexFile;$('latex-file-dialog').addEventListener('cancel',e=>{e.preventDefault();closeLatexFile();});
$('latex-file-save').onclick=async()=>{
  if(!latexOpenedFile||busy)return false;setBusy(true);$('latex-file-status').textContent='正在保存…';
  try{const result=await latexRequest('file',{path:latexOpenedFile.path,text:$('latex-source').value,sha256:latexOpenedFile.sha256,revision:latexFileRevision});
    reconcileLatexState(result.state);folder=result.folder;await openLatexFile(latexOpenedFile.path);renderSections();renderChat();$('save-indicator').textContent='源文件已保存到本地';$('latex-file-status').textContent='源文件和章节已同步。重新编译即可更新 PDF。';return true;
  }catch(e){$('latex-file-status').textContent=e.message;return false;}finally{setBusy(false);}
};
$('latex-compile').onclick=async()=>{
  if(busy||latexCompiling||!project?.latex)return;clearTimeout(inputTimer);if(!await persist())return;
  latexCompiling=true;setBusy(true);$('send').disabled=true;localStatus('正在本地编译 PDF…首次编译可能需要下载宏包，请稍候。');showLatexBuild();
  try{const result=await latexRequest('compile',{},AbortSignal.timeout(270000));await refreshLatexInfo();localStatus(result.ok?'PDF 编译成功，可点击“查看编译 PDF”。':'编译失败，请展开“编译日志”查看具体错误。');}
  catch(e){localStatus(e.message);try{await refreshLatexInfo();}catch{}}
  finally{latexCompiling=false;setBusy(false);showLatexBuild();}
};
let latexPage=1,latexPages=1;
function showLatexPage(){
  $('latex-pdf-image').src='/api/latex/pdf-page?'+latexQuery({page:latexPage,v:latexInfo.compiled?.runId||''});
  $('latex-page-count').textContent=latexPage+' / '+latexPages;$('latex-page-prev').disabled=latexPage<=1;$('latex-page-next').disabled=latexPage>=latexPages;
}
$('latex-page-prev').onclick=()=>{if(latexPage>1){latexPage--;showLatexPage();}};
$('latex-page-next').onclick=()=>{if(latexPage<latexPages){latexPage++;showLatexPage();}};
$('latex-preview').onclick=async()=>{try{await refreshLatexInfo();const details=await localAPI('/api/latex/pdf-info?'+latexQuery());latexPages=details.pages;latexPage=1;showLatexPage();$('latex-pdf-open').href='/api/latex/pdf?'+latexQuery({v:latexInfo.compiled?.runId||''});$('latex-pdf-dialog').showModal();}catch(e){localStatus(e.message);}};
$('latex-pdf-close').onclick=()=>$('latex-pdf-dialog').close();
async function exportLatex(){if(!project?.latex||busy)return;clearTimeout(inputTimer);if(!await persist())return;const a=document.createElement('a');a.href='/api/latex/export?'+latexQuery();a.download=(project.name||'project')+'.zip';document.body.append(a);a.click();a.remove();}
$('latex-export').onclick=exportLatex;
const beforeLatexBackup=$('backup').onclick;$('backup').onclick=()=>project?.latex?exportLatex():beforeLatexBackup();
window.addEventListener('beforeunload',e=>{if(fileDirty()){e.preventDefault();e.returnValue='';}});
