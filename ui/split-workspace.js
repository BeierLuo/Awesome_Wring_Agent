'use strict';
// A persistent writing/PDF workspace; manuscript edits still require explicit saving.
(() => {
  const main=document.querySelector('main'),sidebar=document.querySelector('aside');
  const top=$('workspace-topbar'),tabs=$('workspace-tabs'),pane=$('pdf-pane'),divider=$('pdf-divider');
  const originalHeader=main.querySelector('header');
  document.body.prepend(top);document.body.classList.add('split-workspace');
  $('workspace-project').append($('project-picker'));
  $('workspace-save').append($('save-indicator'));
  $('workspace-language').append($('language-switch'));
  top.insertBefore($('export'),$('workspace-language'));
  $('export').classList.add('topbar-export');
  sidebar.querySelector('.brand').remove();sidebar.querySelector('label[for="project-picker"]').hidden=true;
  originalHeader.classList.add('writing-header');main.prepend(tabs);main.append($('source-pane'));
  main.after(divider,pane);
  sidebar.prepend($('sections-panel'));
  const projectTools=document.createElement('details');projectTools.id='workspace-tools';
  const toolsTitle=document.createElement('summary');toolsTitle.textContent='项目与设置';projectTools.append(toolsTitle);
  const excluded=new Set([$('sections-panel')]);
  for(const node of [...sidebar.children])if(!excluded.has(node))projectTools.append(node);
  sidebar.append(projectTools);
  $('sections-panel').querySelector('.section-heading').textContent='章节目录';
  for(const id of ['latex-file-picker','latex-file-meta','latex-source','latex-file-save','latex-file-status'])$('source-fields').append($(id));
  $('latex-source').rows=20;
  let mode='assistant',workspace=null,previewKey='',loadingKey='',generation=0,sourceGeneration=0;
  let pageCount=0,zoom=1,fitMode='page',previewVisible=true,sourceLoading=false,sourceWorkspace=null,sourceHash=null,observer=null;
  const source=$('latex-source'),scroller=$('pdf-scroll');
  const prompt=$('prompt'),compose=main.querySelector('.compose-area');
  const composeGrip=document.createElement('div');
  composeGrip.id='compose-resize';composeGrip.tabIndex=0;
  composeGrip.setAttribute('role','separator');composeGrip.setAttribute('aria-orientation','horizontal');
  composeGrip.setAttribute('aria-controls','prompt');
  composeGrip.title=document.documentElement.lang==='en'?'Drag to resize; double-click to reset':'\u4e0a\u4e0b\u62d6\u52a8\u8c03\u6574\u9ad8\u5ea6\uff0c\u53cc\u51fb\u6062\u590d';
  composeGrip.setAttribute('aria-label',composeGrip.title);$('form').prepend(composeGrip);
  let composeHeight=96,composeDrag=null;
  try{const saved=Number(localStorage.getItem('draft.composeHeight'));if(saved>=48&&saved<=2000)composeHeight=saved;}catch{}
  function sizeComposer(persist=false){
    if(main.classList.contains('source-mode'))return;
    const fixed=[...main.children].filter(el=>el!==compose&&el.id!=='messages').reduce((sum,el)=>sum+el.getBoundingClientRect().height,0);
    const overhead=compose.getBoundingClientRect().height-prompt.getBoundingClientRect().height;
    const max=Math.max(48,main.clientHeight-fixed-overhead-120);
    const height=Math.round(Math.max(48,Math.min(composeHeight,max)));
    prompt.style.height=height+'px';
    composeGrip.setAttribute('aria-valuemin','48');composeGrip.setAttribute('aria-valuemax',String(Math.round(max)));composeGrip.setAttribute('aria-valuenow',String(height));
    if(persist){composeHeight=height;try{localStorage.setItem('draft.composeHeight',height);}catch{}}
  }
  composeGrip.onpointerdown=event=>{
    if(event.button!==0)return;
    event.preventDefault();composeDrag={y:event.clientY,height:prompt.getBoundingClientRect().height};
    composeGrip.setPointerCapture(event.pointerId);document.body.classList.add('resizing-compose');
  };
  composeGrip.onpointermove=event=>{if(!composeDrag)return;composeHeight=composeDrag.height+composeDrag.y-event.clientY;sizeComposer(true);};
  composeGrip.onpointerup=composeGrip.onpointercancel=event=>{if(composeGrip.hasPointerCapture(event.pointerId))composeGrip.releasePointerCapture(event.pointerId);composeDrag=null;document.body.classList.remove('resizing-compose');};
  composeGrip.onlostpointercapture=()=>{composeDrag=null;document.body.classList.remove('resizing-compose');};
  composeGrip.ondblclick=()=>{composeHeight=96;sizeComposer(true);};
  composeGrip.onkeydown=event=>{
    if(!['ArrowUp','ArrowDown','Home','End'].includes(event.key))return;
    event.preventDefault();composeHeight=event.key==='Home'?48:event.key==='End'?Number(composeGrip.getAttribute('aria-valuemax')):Number(composeGrip.getAttribute('aria-valuenow'))+(event.key==='ArrowUp'?20:-20);sizeComposer(true);
  };
  window.addEventListener('resize',()=>sizeComposer());
  if(typeof ResizeObserver!=='undefined'){
    const composeObserver=new ResizeObserver(()=>sizeComposer());
    for(const el of [main,$('draft-panel'),$('status')])if(el)composeObserver.observe(el);
  }
  requestAnimationFrame(()=>sizeComposer());
  const pdfToolbar=pane.querySelector('.pdf-toolbar');
  pdfToolbar.append(pane.querySelector('.pdf-navigation'));
  const fitPage=document.createElement('button');fitPage.id='pdf-fit-page';
  fitPage.textContent=document.documentElement.lang==='en'?'Fit page':'\u6574\u9875';
  fitPage.setAttribute('aria-pressed','true');$('pdf-fit').before(fitPage);
  let zoomFrame=0;
  const feedback=text=>{$('pdf-feedback').textContent=text;$('pdf-feedback').hidden=!text;};
  function setMode(value){
    mode=value;main.classList.toggle('source-mode',value==='source');$('source-pane').hidden=value!=='source';
    $('tab-assistant').setAttribute('aria-selected',String(value==='assistant'));$('tab-source').setAttribute('aria-selected',String(value==='source'));
    if(value==='assistant')requestAnimationFrame(()=>sizeComposer());
  }
  function sourceState(){
    $('source-state').textContent=sourceLoading?'正在读取文件…':fileDirty()?'未保存的修改':'已保存';
    source.disabled=busy||sourceLoading;$('latex-file-picker').disabled=busy||sourceLoading;
    $('latex-file-save').disabled=busy||sourceLoading||!latexOpenedFile||!fileDirty();
  }
  async function openSource(path=selected()?.source_file||project?.latex?.main){
    if(!project?.latex||busy||sourceLoading)return;
    if(sourceWorkspace===project.id&&latexOpenedFile?.path===path&&(fileDirty()||sourceHash===project.latex.sourceHash)){setMode('source');sourceState();return;}
    if(fileDirty()&&!confirm('放弃尚未保存的源文件编辑？'))return;
    const id=project.id,token=++sourceGeneration;sourceLoading=true;setMode('source');sourceState();
    $('latex-file-status').textContent='';
    try{
      clearTimeout(inputTimer);if(!await persist())return;
      const data=await localAPI('/api/latex/file?'+new URLSearchParams({workspaceId:id,path}));
      if(project?.id!==id||token!==sourceGeneration)return;
      latexOpenedFile=data;latexFileRevision=data.revision;sourceWorkspace=id;sourceHash=project.latex.sourceHash;
      source.value=data.text;source.hidden=false;$('latex-file-meta').textContent=data.path;
      $('latex-file-picker').replaceChildren(...project.latex.files.map(file=>{const option=new Option(file.path,file.path);option.disabled=!file.editable||file.size>2*1024*1024;return option;}));
      $('latex-file-picker').value=path;
      const section=selected();if(section?.source_file===path&&section.text){const start=data.text.indexOf(section.text);if(start>=0)source.setSelectionRange(start,start);}
    }catch(error){$('latex-file-status').textContent=error.message;}
    finally{if(token===sourceGeneration){sourceLoading=false;sourceState();}}
  }
  $('tab-source').onclick=()=>openSource();$('tab-assistant').onclick=()=>setMode('assistant');
  tabs.onkeydown=event=>{if(!['ArrowLeft','ArrowRight'].includes(event.key)||!event.target.matches('[role="tab"]'))return;event.preventDefault();const target=event.key==='ArrowLeft'?$('tab-assistant'):$('tab-source');target.focus();target.click();};
  $('latex-files').onclick=()=>openSource();$('latex-file-picker').onchange=async()=>{const path=$('latex-file-picker').value;await openSource(path);if(latexOpenedFile)$('latex-file-picker').value=latexOpenedFile.path;};
  source.addEventListener('input',sourceState);
  const saveSource=$('latex-file-save').onclick;
  $('latex-file-save').onclick=async()=>{await saveSource();if(!fileDirty())sourceHash=project?.latex?.sourceHash;sourceState();update();};
  const editSection=$('draft-edit').onclick;
  $('draft-edit').onclick=$('edit-section').onclick=()=>project?.latex?openSource():editSection();
  // Prevent leaving an unsaved source file via project controls or section navigation.
  document.addEventListener('click',event=>{
    if(!event.target.closest('#new,#manage-projects,#reload-project,#language-switch,#workspace-home,.section-item,#tab-source'))return;
    if(sourceLoading){event.preventDefault();event.stopImmediatePropagation();return;}
    if(!fileDirty()||event.target.closest('#tab-source'))return;
    if(!confirm('放弃尚未保存的源文件编辑？')){event.preventDefault();event.stopImmediatePropagation();}
    else{source.value=latexOpenedFile.text;sourceState();}
  },true);
  const loadBefore=loadProject;
  loadProject=async function(id){
    if(fileDirty()&&!confirm('放弃尚未保存的源文件编辑？')){$('project-picker').value=project.id;return;}
    await loadBefore(id);update();
  };
  function resetWorkspace(){
    workspace=project?.id||null;previewKey='';loadingKey='';generation++;sourceGeneration++;sourceLoading=false;
    latexOpenedFile=null;sourceWorkspace=null;source.value='';$('latex-file-picker').replaceChildren();$('latex-file-meta').textContent='';$('latex-file-status').textContent='';
    observer?.disconnect();$('pdf-pages').replaceChildren();pageCount=0;setPage(1);feedback('');setMode('assistant');
  }
  function setPage(number){
    const page=Math.max(1,Math.min(pageCount||1,number));$('pdf-page-input').value=page;
    $('pdf-page-input').max=Math.max(1,pageCount);$('pdf-total').textContent='/ '+(pageCount||'—');
    $('pdf-prev').disabled=page<=1;$('pdf-next').disabled=page>=pageCount;
    $('pdf-page-input').disabled=!pageCount;
  }
  function scrollToPage(number){const page=Math.max(1,Math.min(pageCount,Number(number)||1));setPage(page);applyZoom();const sheet=$('pdf-pages').children[page-1];if(sheet)scroller.scrollTo({top:sheet.offsetTop-$('pdf-pages').offsetTop,behavior:'instant'});}
  function applyZoom(){
    const page=Number($('pdf-page-input').value)||1;
    const sheet=$('pdf-pages').children[page-1]||$('pdf-pages').firstElementChild;
    const style=getComputedStyle(scroller);
    const availableWidth=scroller.clientWidth-parseFloat(style.paddingLeft||0)-parseFloat(style.paddingRight||0);
    const availableHeight=scroller.clientHeight-parseFloat(style.paddingTop||0)-parseFloat(style.paddingBottom||0)-2;
    if(fitMode==='page'&&sheet&&availableWidth>0&&availableHeight>0){
      const parts=(sheet.style.aspectRatio||'0.773').split('/').map(Number);
      const ratio=parts.length===2?parts[0]/parts[1]:parts[0];
      zoom=Math.min(1,availableHeight*ratio/availableWidth);
    }else if(fitMode==='width')zoom=1;
    $('pdf-pages').style.width=(zoom*100)+'%';$('pdf-zoom-value').textContent=Math.round(zoom*100)+'%';
    $('pdf-zoom-out').disabled=zoom<=0.2;$('pdf-zoom-in').disabled=zoom>=2;
    fitPage.setAttribute('aria-pressed',String(fitMode==='page'));
    $('pdf-fit').setAttribute('aria-pressed',String(fitMode==='width'));
  }
  function zoomToCurrentPage(){
    const page=Number($('pdf-page-input').value)||1;applyZoom();
    const sheet=$('pdf-pages').children[page-1];
    if(sheet)scroller.scrollTo({top:sheet.offsetTop-$('pdf-pages').offsetTop,behavior:'instant'});
  }
  function scheduleFit(){
    if(!fitMode)return;cancelAnimationFrame(zoomFrame);
    zoomFrame=requestAnimationFrame(zoomToCurrentPage);
  }
  if(typeof ResizeObserver!=='undefined')new ResizeObserver(scheduleFit).observe(scroller);
  window.addEventListener('resize',scheduleFit);
  $('pdf-zoom-in').onclick=()=>{fitMode=null;zoom=Math.min(2,zoom+0.1);zoomToCurrentPage();};
  $('pdf-zoom-out').onclick=()=>{fitMode=null;zoom=Math.max(0.2,zoom-0.1);zoomToCurrentPage();};
  $('pdf-fit').onclick=()=>{fitMode='width';zoomToCurrentPage();};
  fitPage.onclick=()=>{fitMode='page';zoomToCurrentPage();};
  $('pdf-prev').onclick=()=>scrollToPage(Number($('pdf-page-input').value)-1);
  $('pdf-next').onclick=()=>scrollToPage(Number($('pdf-page-input').value)+1);
  $('pdf-page-input').onchange=()=>scrollToPage($('pdf-page-input').value);
  scroller.addEventListener('scroll',()=>{
    const sheets=[...$('pdf-pages').children];if(!sheets.length)return;
    const top=scroller.getBoundingClientRect().top;
    const index=sheets.findIndex(sheet=>sheet.getBoundingClientRect().bottom>top+50);
    if(index>=0)setPage(index+1);
  },{passive:true});
  async function refreshPreview(){
    const compiled=latexInfo?.workspaceId===project?.id?latexInfo.compiled:null;
    if(!compiled||!previewVisible)return;
    const id=project.id,key=id+':'+(compiled.runId||compiled.at);
    if(key===previewKey||key===loadingKey)return;
    const token=++generation,previousPage=Number($('pdf-page-input').value)||1;loadingKey=key;feedback('正在更新 PDF 预览…');
    try{
      const details=await localAPI('/api/latex/pdf-info?'+new URLSearchParams({workspaceId:id,v:compiled.runId||compiled.at}));
      if(token!==generation||project?.id!==id)return;
      const fragment=document.createDocumentFragment();observer?.disconnect();
      if(typeof IntersectionObserver!=='undefined')observer=new IntersectionObserver(entries=>{for(const entry of entries)if(entry.isIntersecting){const image=entry.target;if(image.dataset.src){image.src=image.dataset.src;delete image.dataset.src;}observer.unobserve(image);}},{root:scroller,rootMargin:'800px'});
      for(let number=1;number<=details.pages;number++){
        const sheet=document.createElement('figure');sheet.className='pdf-sheet';
        const size=details.sizes?.[number-1];if(size?.[0]>0&&size?.[1]>0)sheet.style.aspectRatio=size[0]+'/'+size[1];
        const image=document.createElement('img');image.alt='编译 PDF 页面'+' '+number;image.decoding='async';
        const url='/api/latex/pdf-page?'+new URLSearchParams({workspaceId:id,page:number,v:compiled.runId||compiled.at});
        if(number===Math.min(previousPage,details.pages)||!observer)image.src=url;else image.dataset.src=url;
        image.onerror=()=>{if(token===generation)feedback('PDF 页面加载失败，请重新打开预览。');};
        sheet.append(image);fragment.append(sheet);
      }
      $('pdf-pages').replaceChildren(fragment);pageCount=details.pages;previewKey=key;
      $('pdf-empty').hidden=true;setPage(previousPage);applyZoom();
      $('pdf-open').href='/api/latex/pdf?'+new URLSearchParams({workspaceId:id,v:compiled.runId||compiled.at});
      for(const image of $('pdf-pages').querySelectorAll('img[data-src]'))observer?.observe(image);
      feedback('');requestAnimationFrame(()=>{if(token===generation)zoomToCurrentPage();});
    }catch(error){if(token===generation)feedback(error.message);}
    finally{if(token===generation)loadingKey='';}
  }
  function update(){
    if(workspace!==(project?.id||null))resetWorkspace();
    const latex=!!project?.latex,visible=latex&&previewVisible;
    if(selected())$('draft-name').textContent=selected().title;
    document.body.classList.toggle('has-pdf-pane',visible);pane.hidden=!visible;divider.hidden=!visible;
    $('pdf-toggle').hidden=!latex;$('pdf-toggle').setAttribute('aria-expanded',String(visible));$('tab-source').hidden=!latex;
    if(!latex){setMode('assistant');return;}
    $('pdf-recompile').disabled=busy||latexCompiling||sourceLoading;sourceState();
    const info=latexInfo?.workspaceId===project.id?latexInfo:null,compiled=info?.compiled;
    const stale=compiled&&compiled.sourceHash!==project.latex.sourceHash;
    const failed=info?.lastBuild&&!info.lastBuild.ok;
    const state=latexCompiling?'compiling':failed?'failed':stale?'stale':compiled?'ready':'empty';
    pane.dataset.buildState=state;
    $('pdf-build-label').textContent=latexCompiling?'正在编译…':failed?(compiled?'编译失败 · 保留上次 PDF':'编译失败'):stale?'源码已修改 · 请重新编译':compiled?'PDF 已更新':'尚未编译';
    $('pdf-build-log').textContent=[info?.lastBuild?.error,info?.lastBuild?.log].filter(Boolean).join('\n')||'尚未编译。';
    $('pdf-empty').hidden=!!pageCount;$('pdf-open').hidden=!compiled;
    if(!compiled){$('pdf-pages').replaceChildren();pageCount=0;previewKey='';setPage(1);}
    void refreshPreview();
  }
  $('pdf-toggle').onclick=()=>{previewVisible=!previewVisible;update();};
  $('latex-preview').onclick=()=>{previewVisible=true;previewKey='';update();};
  const compileBefore=$('latex-compile').onclick;
  $('pdf-recompile').onclick=$('latex-compile').onclick=async()=>{
    if(fileDirty()){feedback('请先保存源码，再重新编译。');setMode('source');return;}
    await compileBefore();update();
  };
  $('pdf-logs').onclick=()=>{const open=$('pdf-build-log').hidden;$('pdf-build-log').hidden=!open;$('pdf-logs').setAttribute('aria-expanded',String(open));};
  const renderBefore=renderLatexProject;renderLatexProject=function(){renderBefore();update();};
  const buildBefore=showLatexBuild;showLatexBuild=function(){buildBefore();update();};
  const sectionsBefore=renderSections;renderSections=function(){sectionsBefore();if(mode==='source'&&!fileDirty())void openSource();update();};
  function resize(percent){const value=Math.max(30,Math.min(65,percent));document.body.style.setProperty('--write-fr',(100-value)+'fr');document.body.style.setProperty('--pdf-fr',value+'fr');divider.setAttribute('aria-valuenow',Math.round(value));try{localStorage.setItem('draft.pdfWidth',value);}catch{}}
  try{const value=Number(localStorage.getItem('draft.pdfWidth'));if(value>=30&&value<=65)resize(value);}catch{}
  divider.onpointerdown=event=>{if(event.button!==0)return;divider.setPointerCapture(event.pointerId);document.body.classList.add('resizing-pdf');};
  divider.onpointermove=event=>{if(!divider.hasPointerCapture(event.pointerId))return;const remaining=window.innerWidth-sidebar.getBoundingClientRect().width;resize((window.innerWidth-event.clientX)/remaining*100);};
  divider.onpointerup=divider.onpointercancel=event=>{if(divider.hasPointerCapture(event.pointerId))divider.releasePointerCapture(event.pointerId);document.body.classList.remove('resizing-pdf');};
  divider.onkeydown=event=>{if(!['ArrowLeft','ArrowRight','Home'].includes(event.key))return;event.preventDefault();resize(event.key==='Home'?50:Number(divider.getAttribute('aria-valuenow'))+(event.key==='ArrowLeft'?2:-2));};
  update();
  top.hidden=false;tabs.hidden=false;
})();
