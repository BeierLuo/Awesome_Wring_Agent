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
  const sidebarGrip=document.createElement('div');sidebarGrip.id='sidebar-resize';sidebarGrip.tabIndex=0;
  sidebarGrip.setAttribute('role','separator');sidebarGrip.setAttribute('aria-orientation','vertical');
  sidebar.id='workspace-sidebar';sidebarGrip.setAttribute('aria-controls',sidebar.id);
  sidebarGrip.setAttribute('aria-label',document.documentElement.lang==='en'?'Resize sidebar':'调整左侧栏宽度');
  sidebarGrip.title=document.documentElement.lang==='en'?'Drag to resize; double-click to reset':'拖动调整左侧栏宽度，双击恢复';
  document.body.append(sidebarGrip);
  let sidebarWidth=null,sidebarDrag=null,sidebarFrame=0;
  try{const saved=Number(localStorage.getItem('caret.sidebarWidth'));if(saved>=140&&saved<=400)sidebarWidth=saved;}catch{}
  const defaultSidebarWidth=()=>window.innerWidth>=1400?225:window.innerWidth>1000?210:160;
  function sizeSidebar(persist=false){
    if(window.innerWidth<=760)return;
    const maximum=Math.max(140,Math.min(400,window.innerWidth-480));
    const width=Math.max(140,Math.min(maximum,sidebarWidth??defaultSidebarWidth()));
    document.body.style.setProperty('--sidebar-width',width+'px');
    sidebarGrip.setAttribute('aria-valuemin',140);sidebarGrip.setAttribute('aria-valuemax',maximum);sidebarGrip.setAttribute('aria-valuenow',Math.round(width));
    if(persist){sidebarWidth=width;try{localStorage.setItem('caret.sidebarWidth',width);}catch{}}
  }
  sidebarGrip.onpointerdown=event=>{
    if(event.button!==0||window.innerWidth<=760)return;
    event.preventDefault();sidebarDrag={x:event.clientX,width:sidebar.getBoundingClientRect().width};
    sidebarGrip.setPointerCapture(event.pointerId);document.body.classList.add('resizing-sidebar');
  };
  sidebarGrip.onpointermove=event=>{
    if(!sidebarDrag)return;
    sidebarWidth=sidebarDrag.width+event.clientX-sidebarDrag.x;
    if(!sidebarFrame)sidebarFrame=requestAnimationFrame(()=>{sidebarFrame=0;sizeSidebar();});
  };
  function finishSidebarResize(){
    if(!sidebarDrag)return;
    cancelAnimationFrame(sidebarFrame);sidebarFrame=0;sizeSidebar(true);sidebarDrag=null;document.body.classList.remove('resizing-sidebar');
  }
  sidebarGrip.onpointerup=sidebarGrip.onpointercancel=event=>{
    finishSidebarResize();if(sidebarGrip.hasPointerCapture(event.pointerId))sidebarGrip.releasePointerCapture(event.pointerId);
  };
  sidebarGrip.onlostpointercapture=finishSidebarResize;
  sidebarGrip.ondblclick=()=>{sidebarWidth=null;try{localStorage.removeItem('caret.sidebarWidth');}catch{}sizeSidebar();};
  sidebarGrip.onkeydown=event=>{
    if(!['ArrowLeft','ArrowRight','Home'].includes(event.key))return;
    event.preventDefault();
    if(event.key==='Home'){sidebarGrip.ondblclick();return;}
    sidebarWidth=Number(sidebarGrip.getAttribute('aria-valuenow'))+(event.key==='ArrowRight'?10:-10);sizeSidebar(true);
  };
  window.addEventListener('resize',()=>sizeSidebar());sizeSidebar();

  $('sections-panel').querySelector('.section-heading').textContent='章节目录';
  for(const id of ['latex-file-picker','latex-file-meta','latex-source','latex-file-save','latex-file-status'])$('source-fields').append($(id));
  $('latex-source').rows=20;
  let mode='assistant',workspace=null,previewKey='',loadingKey='',generation=0,sourceGeneration=0;
  let pageCount=0,zoom=1,fitMode='page',previewVisible=true,sourceLoading=false,sourceWorkspace=null,sourceHash=null,observer=null;
  const source=$('latex-source'),scroller=$('pdf-scroll');
  const prompt=$('prompt'),compose=main.querySelector('.compose-area');
  // The selected label determines the width, not the longest menu option.
  for(const id of ['composer-model','composer-effort']){
    const picker=$(id),control=document.createElement('div'),label=document.createElement('span');
    control.className='composer-choice '+id+'-choice';
    label.className='composer-choice-size';label.setAttribute('aria-hidden','true');
    picker.before(control);control.append(label,picker);
    const sync=()=>{label.textContent=picker.selectedOptions[0]?.textContent||'';};
    picker.addEventListener('change',sync);
    new MutationObserver(sync).observe(picker,{childList:true,subtree:true,characterData:true,attributes:true});
    sync();
  }

  const passageCard=document.createElement('div');passageCard.id='passage-target';passageCard.hidden=true;
  const passageLabel=document.createElement('strong'),passageClear=document.createElement('button');
  passageClear.type='button';passageClear.textContent='取消选择';
  const passageDetails=document.createElement('details'),passageSummary=document.createElement('summary'),passageSource=document.createElement('pre');
  passageSummary.textContent='查看选中 TeX';passageDetails.append(passageSummary,passageSource);passageCard.append(passageLabel,passageClear,passageDetails);compose.prepend(passageCard);
  const selectionAction=document.createElement('button');selectionAction.id='pdf-edit-selection';selectionAction.type='button';selectionAction.textContent='修改这一段落';selectionAction.hidden=true;
  document.body.append(selectionAction);
  let passageCandidate=null,passagePending=false,highlightRequestKey='';
  // Paint opaque row shapes in one translucent layer: intersections never darken.
  function passageRows(boxes){
    const rows=[];
    for(const box of [...boxes].sort((a,b)=>a[2]-b[2]||a[1]-b[1])){
      const [page,x,y,w,h]=box;
      const row=rows.find(r=>r[0]===page&&Math.abs(r[2]+r[4]/2-y-h/2)<Math.min(r[4],h)*.45&&x<=r[1]+r[3]+Math.max(h,r[4])&&x+w>=r[1]-Math.max(h,r[4]));
      if(row){const right=Math.max(row[1]+row[3],x+w),bottom=Math.max(row[2]+row[4],y+h);row[1]=Math.min(row[1],x);row[2]=Math.min(row[2],y);row[3]=right-row[1];row[4]=bottom-row[2];}
      else rows.push([...box]);
    }
    return rows;
  }
  function glyphBox(g){return [JSON.parse(g.dataset.pdfPoint)[0],...['left','top','width','height'].map(k=>parseFloat(g.style[k]))];}
  function highlightRows(boxes){return passageRows(boxes).map(r=>r.map(n=>Math.round(n*10000)/10000));}
  function rowMarks(rows,className){return rows.map(r=>{
    const box=document.createElement('span');box.className=className;
    Object.assign(box.style,{left:r[1]+'%',top:r[2]+'%',width:r[3]+'%',height:r[4]+'%'});return box;
  });}
  function paintLiveSelection(){
    const selection=window.getSelection(),pages=$('pdf-pages');
    const range=selection?.rangeCount&&!selection.isCollapsed?selection.getRangeAt(0):null;
    const valid=range&&pages.contains(range.startContainer)&&pages.contains(range.endContainer);
    for(const sheet of pages.children){
      let layer=sheet.querySelector('.pdf-selection-layer');
      const glyphs=valid?[...sheet.querySelectorAll('.pdf-text-char')].filter(g=>range.intersectsNode(g)):[];
      if(!glyphs.length){layer?.remove();continue;}
      const rows=highlightRows(glyphs.map(glyphBox)),key=JSON.stringify(rows);
      if(layer?.dataset.boxes===key)continue;
      if(!layer){layer=document.createElement('div');layer.className='pdf-selection-layer';layer.setAttribute('aria-hidden','true');sheet.append(layer);}
      layer.dataset.boxes=key;layer.replaceChildren(...rowMarks(rows,'pdf-selection-mark'));
    }
  }
  let selectionFrame=0;
  document.addEventListener('selectionchange',()=>{
    if(selectionFrame)return;
    selectionFrame=requestAnimationFrame(()=>{selectionFrame=0;paintLiveSelection();if(window.getSelection()?.isCollapsed)hidePassageAction();});
  });
  function paintPassage(){
    const focus=selected()?.paragraphTarget,highlight=focus?.pdfHighlight;
    let valid=!!focus;try{W.selectionRequest(selected());}catch{valid=false;}
    const rects=valid&&!focus.stale&&Array.isArray(highlight?.rects)?highlight.rects:[];
    for(const sheet of $('pdf-pages').children){
      const number=Number(sheet.querySelector('img')?.dataset.page);
      const boxes=highlightRows(rects.filter(r=>r[0]===number&&sheet.dataset.runId===highlight?.runId)),key=JSON.stringify(boxes);
      let layer=sheet.querySelector('.pdf-passage-layer');
      if(layer?.dataset.boxes===key)continue;
      if(!boxes.length){layer?.remove();continue;}
      // Hand the existing selection overlay to the confirmed passage without a repaint.
      const live=sheet.querySelector('.pdf-selection-layer');
      if(live?.dataset.boxes===key){
        layer?.remove();live.className='pdf-passage-layer';
        for(const mark of live.children)mark.className='pdf-passage-mark';
        continue;
      }
      if(!layer){layer=document.createElement('div');layer.className='pdf-passage-layer';layer.setAttribute('aria-hidden','true');sheet.append(layer);}
      layer.dataset.boxes=key;layer.replaceChildren(...rowMarks(boxes,'pdf-passage-mark'));
    }
  }
  async function refreshPassageHighlight(){
    const s=selected(),focus=s?.paragraphTarget,compiled=latexInfo?.compiled,id=project?.id;
    if(!focus||focus.stale||!compiled||compiled.sourceHash!==project?.latex?.sourceHash)return;
    if(focus.pdfHighlight?.runId===compiled.runId&&focus.pdfHighlight.complete)return;
    let request;try{request=W.selectionRequest(s);}catch{return;}
    const key=JSON.stringify([id,s.id,focus.version,compiled.runId,request.start,request.end]);
    if(highlightRequestKey===key)return;highlightRequestKey=key;
    try{
      const data=await localAPI('/api/latex/selection-highlight?'+new URLSearchParams({workspaceId:id,v:compiled.runId,sectionId:s.id,start:request.start,end:request.end,version:focus.version}));
      if(project?.id!==id||selected()?.paragraphTarget!==focus||latexInfo?.compiled?.runId!==compiled.runId||s.versions.at(-1)?.id!==request.version)return;
      if(data.runId!==compiled.runId||!Array.isArray(data.rects)||!data.rects.length)throw new Error('PDF 高亮位置无效');
      focus.pdfHighlight={...data,complete:true};paintPassage();
      // Save coordinates so focusing the composer and reloading retain the highlight.
      await persist();
    }catch(error){if(project?.id===id&&selected()?.paragraphTarget===focus)feedback('PDF 高亮暂未恢复：'+error.message);}
  }
  function hidePassageAction(){selectionAction.hidden=true;passageCandidate=null;}
  function positionPassageAction(){
    if(selectionAction.hidden||!passageCandidate)return;
    if(pane.hidden){hidePassageAction();return;}
    const bounds=scroller.getBoundingClientRect(),range=passageCandidate.range;
    const rects=range?.getClientRects?[...range.getClientRects()]:[];
    const anchor=rects.filter(r=>r.bottom>Math.max(0,bounds.top)&&r.top<Math.min(window.innerHeight,bounds.bottom)).at(-1);
    if(!anchor){if(rects.length)selectionAction.hidden=true;return;}
    const width=selectionAction.offsetWidth||166,height=selectionAction.offsetHeight||40;
    const left=Math.max(8,Math.min(window.innerWidth-width-8,Math.max(bounds.left+8,Math.min(bounds.right-width-8,(anchor.left+anchor.right-width)/2))));
    let top=anchor.top-height-8;
    if(top<Math.max(8,bounds.top+8))top=anchor.bottom+8;
    top=Math.max(8,Math.min(window.innerHeight-height-8,top));
    selectionAction.style.left=left+'px';selectionAction.style.top=top+'px';
  }
  scroller.addEventListener('scroll',positionPassageAction);window.addEventListener('resize',positionPassageAction);
  document.addEventListener('pointerdown',e=>{if(!scroller.contains(e.target)&&!selectionAction.contains(e.target))hidePassageAction();});
  document.addEventListener('keydown',e=>{if(e.key==='Escape')hidePassageAction();});

  function renderPassage(){
    const s=selected(),focus=s?.paragraphTarget;passageCard.hidden=!focus;
    paintPassage();void refreshPassageHighlight();
    passageClear.disabled=busy;selectionAction.disabled=busy||passagePending;
    if(!focus)return;
    let valid=true;try{W.selectionRequest(s);}catch{valid=false;}
    passageLabel.textContent=valid?'已选段落 · 后续提问默认针对这一段':'选中段落已变化 · 请重新选择或取消';
    passageSource.textContent=(s.source_file||'')+'\n\n'+focus.text;
    passageCard.dataset.stale=String(!valid);
  }
  passageClear.onclick=async()=>{if(busy)return;delete selected().paragraphTarget;highlightRequestKey='';hidePassageAction();renderPassage();await persist();};
  function capturePassage(){
    paintLiveSelection();
    if(busy||passagePending)return;
    const selection=window.getSelection(),pages=$('pdf-pages');passageCandidate=null;selectionAction.hidden=true;
    if(!selection?.rangeCount||selection.isCollapsed)return;
    const range=selection.getRangeAt(0);
    if(!pages.contains(range.startContainer)||!pages.contains(range.endContainer))return;
    const points=[],glyphs=[];
    for(const row of pages.querySelectorAll('.pdf-text-line')){
      const chars=[...row.querySelectorAll('.pdf-text-char')].filter(g=>range.intersectsNode(g));
      if(!chars.length)continue;
      glyphs.push(...chars);
      for(const g of new Set([chars[0],chars[Math.floor(chars.length/2)],chars.at(-1)]))points.push(JSON.parse(g.dataset.pdfPoint));
    }
    if(!points.length)return;
    passageCandidate={id:project?.id,runId:latexInfo?.compiled?.runId,points,glyphs,range:range.cloneRange()};selectionAction.hidden=false;positionPassageAction();
  }
  scroller.addEventListener('mouseup',capturePassage);scroller.addEventListener('keyup',capturePassage);
  selectionAction.onpointerdown=e=>e.preventDefault();
  selectionAction.onclick=async()=>{
    const candidate=passageCandidate;
    if(!candidate||busy||passagePending||candidate.id!==project?.id)return;
    if(fileDirty()||latexInfo?.compiled?.sourceHash!==project.latex.sourceHash){feedback('请先保存源码并重新编译，再选择段落。');return;}
    passagePending=true;renderPassage();feedback('');
    try{
      const result=await localAPI('/api/latex/selection?'+new URLSearchParams({workspaceId:candidate.id,v:candidate.runId,points:JSON.stringify(candidate.points)}));
      if(busy||project?.id!==candidate.id||latexInfo?.compiled?.runId!==candidate.runId)return;
      if(fileDirty()||latexInfo?.compiled?.sourceHash!==project.latex.sourceHash)throw new Error('请先保存源码并重新编译，再选择段落。');
      const index=sections.findIndex(s=>s.id===result.sectionId),s=sections[index];
      if(!s||s.versions.at(-1)?.id!==result.version)throw new Error('稿件版本已变化，请重新载入后选择段落。');
      const chars=Array.from(s.text),start=chars.slice(0,result.start).join('').length,end=chars.slice(0,result.end).join('').length;
      if(s.text.slice(start,end)!==result.text)throw new Error('选中段落已变化，请重新选择。');
      clearTimeout(inputTimer);
      if(active())active().input=prompt.value;
      const rects=candidate.glyphs.map(glyphBox);
      selectedSection=index;s.paragraphTarget={start,end,text:result.text,version:result.version,pdfHighlight:{runId:candidate.runId,rects,complete:false}};
      highlightRequestKey='';
      setMode('assistant');renderSections();renderChat({latest:true});renderPassage();window.getSelection()?.removeAllRanges();paintLiveSelection();prompt.focus({preventScroll:true});selectionAction.hidden=true;passageCandidate=null;
      if(!await persist())throw new Error('段落选择未保存，请重试。');
    }catch(error){feedback(error.message);}
    finally{passagePending=false;renderPassage();}
  };
  const chatNavigation=document.createElement('div');chatNavigation.id='chat-navigation';
  const latestButton=document.createElement('button');latestButton.id='chat-latest';latestButton.type='button';
  latestButton.textContent=document.documentElement.lang==='en'?'Jump to latest ↓':'\u8df3\u5230\u6700\u65b0\u5bf9\u8bdd \u2193';
  latestButton.setAttribute('aria-controls','messages');
  latestButton.onclick=()=>{$('messages').scrollTo({top:$('messages').scrollHeight,behavior:'smooth'});};
  chatNavigation.append(latestButton);compose.prepend(chatNavigation);
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
  let zoomFrame=0,navigationGeneration=0,feedbackTimer;
  const feedback=(text,duration=0)=>{
    clearTimeout(feedbackTimer);
    $('pdf-feedback').textContent=text;$('pdf-feedback').hidden=!text;
    if(text&&duration)feedbackTimer=setTimeout(()=>feedback(''),duration);
  };
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
  async function jumpToSource(event,image,number,size,id,runId){
    if(busy||sourceLoading||!size||project?.id!==id)return;
    if(fileDirty()){feedback('请先保存源码并重新编译，再定位。');return;}
    if(latexInfo?.compiled?.sourceHash!==project.latex.sourceHash){feedback('源码已修改，请重新编译后定位。');return;}
    const rect=image.getBoundingClientRect();if(!rect.width||!rect.height)return;
    event.preventDefault();
    const token=++navigationGeneration;
    const current=()=>token===navigationGeneration&&project?.id===id&&latexInfo?.compiled?.runId===runId;
    feedback('正在定位源码…');
    try{
      const result=await localAPI('/api/latex/inverse-search?'+new URLSearchParams({workspaceId:id,v:runId,page:number,x:(event.clientX-rect.left)*size[0]/rect.width,y:(event.clientY-rect.top)*size[1]/rect.height}));
      if(!current()||fileDirty())return;
      await openSource(result.path);
      if(!current()||fileDirty()||latexOpenedFile?.path!==result.path)return;
      if(latexOpenedFile.sha256!==result.sha256){feedback('源码已修改，请重新编译后定位。');return;}
      const lines=source.value.split('\n'),line=Math.max(1,Math.min(lines.length,result.line));
      const start=lines.slice(0,line-1).reduce((sum,text)=>sum+text.length+1,0);
      source.focus();source.setSelectionRange(start,start+lines[line-1].length);
      // Measure the wrapped text with the same font/width as the textarea.
      const mirror=document.createElement('div'),style=getComputedStyle(source);
      for(const key of ['font','lineHeight','letterSpacing','padding','border','boxSizing','whiteSpace','overflowWrap','wordBreak','tabSize'])mirror.style[key]=style[key];
      Object.assign(mirror.style,{position:'absolute',visibility:'hidden',width:source.clientWidth+'px',height:'auto'});
      mirror.textContent=source.value.slice(0,start);const marker=document.createElement('span');marker.textContent='|';mirror.append(marker);document.body.append(mirror);
      source.scrollTop=Math.max(0,marker.offsetTop-source.clientHeight/2);source.scrollLeft=0;mirror.remove();
      $('latex-file-status').textContent=result.path+' · '+line;
      feedback('已定位到 '+result.path+' · '+line,5000);
    }catch(error){if(current())feedback(error.message);}
  }
  $('tab-source').onclick=()=>openSource();$('tab-assistant').onclick=()=>setMode('assistant');
  tabs.onkeydown=event=>{if(!['ArrowLeft','ArrowRight'].includes(event.key)||!event.target.matches('[role="tab"]'))return;event.preventDefault();const target=event.key==='ArrowLeft'?$('tab-assistant'):$('tab-source');target.focus();target.click();};
  $('latex-files').onclick=()=>openSource();$('latex-file-picker').onchange=async()=>{const path=$('latex-file-picker').value;await openSource(path);if(latexOpenedFile)$('latex-file-picker').value=latexOpenedFile.path;};
  source.addEventListener('input',sourceState);
  const saveSource=$('latex-file-save').onclick;
  $('latex-file-save').onclick=async()=>{const saved=await saveSource();if(!fileDirty())sourceHash=project?.latex?.sourceHash;sourceState();update();return saved;};
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
    workspace=project?.id||null;highlightRequestKey='';passageCandidate=null;selectionAction.hidden=true;previewKey='';loadingKey='';generation++;sourceGeneration++;navigationGeneration++;sourceLoading=false;
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
  function refitPreservingPosition(){
    // Layout changes (including selection feedback) are not page navigation.
    // Use visible geometry: the page input may still name the preceding page.
    const top=scroller.getBoundingClientRect().top;
    const sheet=[...$('pdf-pages').children].find(item=>item.getBoundingClientRect().bottom>top);
    const before=sheet?.getBoundingClientRect();
    const fraction=before?.height>0?(top-before.top)/before.height:0;
    applyZoom();
    if(before?.height>0){
      const after=sheet.getBoundingClientRect();
      scroller.scrollTo({top:scroller.scrollTop+after.top-top+fraction*after.height,behavior:'instant'});
    }
  }
  function scheduleFit(){
    if(!fitMode)return;cancelAnimationFrame(zoomFrame);
    zoomFrame=requestAnimationFrame(refitPreservingPosition);
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
  let previewRecovery=null;
  const previewCurrent=(id,token)=>token===generation&&project?.id===id;
  async function recoverPreview(id,token){
    if(!previewCurrent(id,token))return false;
    // Coalesce page/image failures: checking the build must not reload source
    // files or discard an unsaved edit in this tab.
    if(!latexCompiling){
      if(previewRecovery?.token!==token){
        const recovery={token};previewRecovery=recovery;
        recovery.promise=(async()=>{
          const info=await localAPI('/api/latex/info?'+new URLSearchParams({workspaceId:id}));
          if(!previewCurrent(id,token))return;
          const previous=latexInfo?.compiled?.runId;
          latexInfo={...info,workspaceId:id};
          if(info.compiled?.runId!==previous)showLatexBuild();
        })().finally(()=>{if(previewRecovery===recovery)previewRecovery=null;});
      }
      await previewRecovery.promise;
    }
    return previewCurrent(id,token);
  }
  async function loadTextLayer(sheet,id,runId,number,token,attempt=0,bundled=null){
    if(sheet.dataset.textLoading)return;
    sheet.dataset.textLoading='true';
    try{
      const data=bundled||await localAPI('/api/latex/pdf-text?'+new URLSearchParams({workspaceId:id,v:runId,page:number}));
      if(token!==generation||project?.id!==id||!sheet.isConnected)return;
      if(!(data.width>0&&data.height>0)||!Array.isArray(data.blocks))throw new Error('PDF 文字层数据无效');
      const layer=document.createElement('div');layer.className='pdf-text-layer';
      for(const block of data.blocks){
        const paragraph=document.createElement('div');paragraph.className='pdf-text-block';
        for(const line of block){
          const row=document.createElement('span');row.className='pdf-text-line';
          for(const [text,x0,y0,x1,y1] of line){
            const glyph=document.createElement('span');glyph.className='pdf-text-char';glyph.textContent=text;glyph.dataset.pdfPoint=JSON.stringify([number,(x0+x1)/2,(y0+y1)/2]);
            Object.assign(glyph.style,{left:x0/data.width*100+'%',top:y0/data.height*100+'%',width:(x1-x0)/data.width*100+'%',height:(y1-y0)/data.height*100+'%',fontSize:(y1-y0)/data.width*100+'cqw'});
            row.append(glyph);
          }
          row.append(document.createTextNode('\n'));paragraph.append(row);
        }
        paragraph.append(document.createTextNode('\n'));layer.append(paragraph);
      }
      sheet.append(layer);paintPassage();
    }catch(error){
      if(!previewCurrent(id,token)||!sheet.isConnected)return;
      sheet.dataset.textLoading='';
      if(attempt<2){
        await new Promise(resolve=>setTimeout(resolve,1000*(attempt+1)));
        try{if(!await recoverPreview(id,token))return;}catch{}
        if(previewCurrent(id,token)&&sheet.isConnected)return loadTextLayer(sheet,id,runId,number,token,attempt+1);
      }else if(!latexCompiling)feedback('PDF 文字层加载失败：'+error.message);
    }
  }
  // Limit remote page work so a long document cannot fill the Mac queue.
  // Keep only a bounded, in-memory cache keyed by the exact compiled version.
  const remotePages=new Map();let remotePageBytes=0,remotePageActive=0;
  const remotePageQueue=[];
  function drainRemotePages(){
    const visiblePage=Number($('pdf-page-input').value)||1;
    remotePageQueue.sort((a,b)=>Math.abs(a.number-visiblePage)-Math.abs(b.number-visiblePage));
    while(remotePageActive<2&&remotePageQueue.length){
      const job=remotePageQueue.shift();if(!previewCurrent(job.id,job.token)||!job.image.isConnected)continue;
      remotePageActive++;
      void loadRemotePage(job).finally(()=>{remotePageActive--;drainRemotePages();});
    }
  }
  async function loadRemotePage({image,id,runId,number,token}){
    const key=id+':'+runId+':'+number;
    for(let attempt=0;attempt<3&&previewCurrent(id,token)&&image.isConnected;attempt++){
      try{
        let data=remotePages.get(key);
        if(!data){
          data=await localAPI('/api/remote/pdf-page?'+new URLSearchParams({workspaceId:id,v:runId,page:number}));
          if(!data.image||!(data.width>0&&data.height>0)||!Array.isArray(data.blocks))throw new Error('PDF 文字层数据无效');
          const bytes=JSON.stringify(data).length*2;
          if(bytes<=16*1024*1024){
            if(remotePages.has(key)){remotePageBytes-=remotePages.get(key).cacheBytes;remotePages.delete(key);}
            while(remotePages.size>=24||remotePageBytes+bytes>16*1024*1024){const oldest=remotePages.keys().next().value;remotePageBytes-=remotePages.get(oldest).cacheBytes;remotePages.delete(oldest);}
            data.cacheBytes=bytes;remotePages.set(key,data);remotePageBytes+=bytes;
          }
        }
        if(!previewCurrent(id,token)||!image.isConnected)return;
        image.src='data:image/png;base64,'+data.image;
        await loadTextLayer(image.parentElement,id,runId,number,token,0,data);return;
      }catch(error){
        if(!previewCurrent(id,token))return;
        if(attempt===2){if(!latexCompiling)feedback('PDF 文字层加载失败：'+error.message);return;}
        await new Promise(resolve=>setTimeout(resolve,1000*(attempt+1)));
        try{if(!await recoverPreview(id,token))return;}catch{}
      }
    }
  }
  // Copy logical lines, avoiding browser-inserted newlines between positioned glyphs.
  document.addEventListener('copy',event=>{
    const selection=window.getSelection();if(!selection?.rangeCount||selection.isCollapsed||!event.clipboardData)return;
    const range=selection.getRangeAt(0),pages=$('pdf-pages');
    if(!pages.contains(range.startContainer)||!pages.contains(range.endContainer))return;
    event.clipboardData.setData('text/plain',range.cloneContents().textContent);event.preventDefault();
  });
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
      const activate=image=>{
        if(window.DraftRemote){
          if(image.dataset.queued)return;image.dataset.queued='true';
          remotePageQueue.push({image,id,runId:compiled.runId,number:Number(image.dataset.page),token});drainRemotePages();
        }else{
          if(image.dataset.src){image.src=image.dataset.src;delete image.dataset.src;}
          void loadTextLayer(image.parentElement,id,compiled.runId,Number(image.dataset.page),token);
        }
      };
      if(typeof IntersectionObserver!=='undefined')observer=new IntersectionObserver(entries=>{for(const entry of entries)if(entry.isIntersecting){activate(entry.target);observer.unobserve(entry.target);}},{root:scroller,rootMargin:window.DraftRemote?'350px':'800px'});
      for(let number=1;number<=details.pages;number++){
        const sheet=document.createElement('figure');sheet.className='pdf-sheet';sheet.dataset.runId=compiled.runId;
        const size=details.sizes?.[number-1];if(size?.[0]>0&&size?.[1]>0)sheet.style.aspectRatio=size[0]+'/'+size[1];
        const image=document.createElement('img');image.alt='编译 PDF 页面'+' '+number;image.decoding='async';
        const url='/api/latex/pdf-page?'+new URLSearchParams({workspaceId:id,page:number,v:compiled.runId||compiled.at});
        if(!window.DraftRemote){if(number===Math.min(previousPage,details.pages)||!observer)image.src=url;else image.dataset.src=url;}
        let imageRetries=0;
        image.onerror=async()=>{
          if(!previewCurrent(id,token))return;
          if(imageRetries++<2){
            await new Promise(resolve=>setTimeout(resolve,1000*imageRetries));
            try{if(!await recoverPreview(id,token))return;}catch{}
            if(previewCurrent(id,token)&&image.isConnected)image.src=url+'&retry='+imageRetries;
          }else if(!latexCompiling)feedback('PDF 页面加载失败，请重新打开预览。');
        };
        image.draggable=false;image.dataset.page=number;
        sheet.addEventListener('dblclick',event=>void jumpToSource(event,image,number,size,id,compiled.runId));
        sheet.append(image);fragment.append(sheet);
      }
      $('pdf-pages').replaceChildren(fragment);pageCount=details.pages;previewKey=key;paintPassage();void refreshPassageHighlight();hidePassageAction();
      $('pdf-empty').hidden=true;setPage(previousPage);applyZoom();
      $('pdf-open').href='/api/latex/pdf?'+new URLSearchParams({workspaceId:id,v:compiled.runId||compiled.at});
      // Start the visible page first, before neighboring pages compete for slots.
      if(window.DraftRemote)activate($('pdf-pages').children[Math.min(previousPage,details.pages)-1].querySelector('img'));
      for(const image of $('pdf-pages').querySelectorAll('img')){if(observer)observer.observe(image);else activate(image);}
      feedback('');requestAnimationFrame(()=>{if(token===generation)zoomToCurrentPage();});
    }catch(error){if(token===generation)feedback(error.message);}
    finally{if(token===generation)loadingKey='';}
  }
  function update(){
    if(workspace!==(project?.id||null))resetWorkspace();
    renderPassage();
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
  let shortcutCompiling=false;
  async function saveAndRecompile(){
    if(shortcutCompiling||busy||latexCompiling||sourceLoading||!project?.latex||document.querySelector('dialog[open]'))return;
    const id=project.id;shortcutCompiling=true;
    try{
      if(fileDirty()){
        const saved=await $('latex-file-save').onclick();
        if(saved===false||fileDirty()){
          feedback('源码未保存成功，已取消重新编译。');setMode('source');return;
        }
      }
      if(project?.id!==id||busy||latexCompiling||sourceLoading)return;
      await $('pdf-recompile').onclick();
    }catch(error){feedback(error.message);}
    finally{shortcutCompiling=false;}
  }
  $('pdf-recompile').title='重新编译（⌘S；自动保存源码）';
  $('pdf-recompile').setAttribute('aria-keyshortcuts','Meta+S');
  document.addEventListener('keydown',event=>{
    if(!event.metaKey||event.ctrlKey||event.altKey||event.shiftKey||event.key.toLowerCase()!=='s'||!project?.latex)return;
    event.preventDefault();
    if(!event.repeat&&!event.isComposing&&event.keyCode!==229)void saveAndRecompile();
  });
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
