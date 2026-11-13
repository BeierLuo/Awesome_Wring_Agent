const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {JSDOM}=require('jsdom');
const root=path.resolve(__dirname,'..');
const dom=new JSDOM(fs.readFileSync(path.join(root,'ui/index.html'),'utf8'),{runScripts:'outside-only',url:'http://127.0.0.1:8769/',pretendToBeVisual:true});
const w=dom.window;w.confirm=()=>true;
let resizePreview;w.ResizeObserver=class{constructor(callback){this.callback=callback;}observe(target){if(target.id==='pdf-scroll')resizePreview=this.callback;}};
w.HTMLElement.prototype.scrollTo=function(){};
w.eval(`
var $=id=>document.getElementById(id),busy=false,latexCompiling=false,inputTimer;
var project={id:'one',latex:{main:'main.tex',sourceHash:'v1',files:[{path:'main.tex',editable:true,size:50}]}},sections=[];
var latexInfo={workspaceId:'one',compiled:{runId:'build1',sourceHash:'v1'},lastBuild:{ok:true}};
var latexOpenedFile=null,latexFileRevision=0,compileCount=0,requests=[],pendingInfo=null;
var selectedSection=0;sections=[{id:'abstract',title:'Abstract',source_file:'main.tex',text:'Original source',versions:[{id:'v1'}],format:'latex'}];
function selected(){return sections[selectedSection];} function active(){return selected();} var lastChatRender=null;function renderChat(options){lastChatRender={id:selected().id,latest:options?.latest};$('prompt').value=selected().input||'';}
function fileDirty(){return latexOpenedFile&&$('latex-source').value!==latexOpenedFile.text;}
function renderLatexProject(){} function showLatexBuild(){} function renderSections(){}
async function persist(){return true;}
async function loadProject(id){project={id,latex:{main:'main.tex',sourceHash:'v1',files:[{path:'main.tex',editable:true,size:50}]}};latexInfo=null;renderLatexProject();}
async function localAPI(url){requests.push(url);if(url.includes('/latex/selection-highlight?'))return {runId:latexInfo.compiled.runId,rects:[[1,10,12.5,2,1.5]]};if(url.includes('/latex/selection?'))return {sectionId:'abstract',path:'main.tex',start:0,end:15,text:'Original source',version:'v1'};if(url.includes('pdf-text'))return {width:600,height:800,blocks:[[[['H',60,100,68,112],['i',68,100,72,112]]]]};if(url.includes('inverse-search'))return {path:'main.tex',line:1,column:0,sha256:'abc'};if(url.includes('pdf-info')){if(pendingInfo)return pendingInfo;return {pages:3,sizes:[[600,800],[600,800],[600,800]]};}return {path:'main.tex',text:'Original source',revision:1,sha256:'abc'};}
$('latex-file-save').onclick=async()=>{latexOpenedFile.text=$('latex-source').value;};
$('draft-edit').onclick=()=>{};
$('latex-compile').onclick=async()=>{compileCount++;latexInfo={workspaceId:project.id,compiled:{runId:'build2',sourceHash:'v1'},lastBuild:{ok:true}};showLatexBuild();};
`);
assert.equal(w.document.getElementById('workspace-topbar').hidden,true,'Uninitialized layout must not appear alongside the old workspace');
assert.equal(w.document.getElementById('workspace-tabs').hidden,true);
let previewWidth=800,previewHeight=600;
Object.defineProperty(w.document.getElementById('pdf-scroll'),'clientWidth',{get:()=>previewWidth});
Object.defineProperty(w.document.getElementById('pdf-scroll'),'clientHeight',{get:()=>previewHeight});
w.eval(fs.readFileSync(path.join(root,'ui/workspace-core.js'),'utf8'));w.eval('var W=WorkspaceCore;');
w.eval(fs.readFileSync(path.join(root,'ui/split-workspace.js'),'utf8'));
assert.ok(w.document.getElementById('conversation-toolbar').contains(w.document.getElementById('new-conversation')));
assert.ok(w.document.getElementById('conversation-toolbar').contains(w.document.getElementById('conversation-picker')));
assert.ok(w.document.getElementById('form').contains(w.document.getElementById('composer-model')));
assert.equal(w.document.getElementById('stop'),null);
const tick=()=>new Promise(r=>setTimeout(r,30));
(async()=>{
 await tick();const $=id=>w.document.getElementById(id);
 assert.equal($('workspace-topbar').hidden,false);assert.equal($('workspace-tabs').hidden,false);
 const sideGrip=$('sidebar-resize'),sidebar=$('workspace-sidebar');
 assert.ok(sideGrip);assert.equal(sideGrip.getAttribute('aria-controls'),sidebar.id);
 sidebar.getBoundingClientRect=()=>({width:210});
 let sideCaptured=false;sideGrip.setPointerCapture=()=>{sideCaptured=true;};sideGrip.hasPointerCapture=()=>sideCaptured;sideGrip.releasePointerCapture=()=>{sideCaptured=false;};
 sideGrip.onpointerdown({button:0,pointerId:1,clientX:210,preventDefault(){}});
 sideGrip.onpointermove({pointerId:1,clientX:300});await tick();
 sideGrip.onpointerup({pointerId:1});
 assert.equal(w.document.body.style.getPropertyValue('--sidebar-width'),'300px');
 assert.equal(w.localStorage.getItem('caret.sidebarWidth'),'300');
 assert.equal(w.document.body.classList.contains('resizing-sidebar'),false);
 sideGrip.onkeydown({key:'ArrowLeft',preventDefault(){}});assert.equal(sideGrip.getAttribute('aria-valuenow'),'290');
 sideGrip.ondblclick();assert.equal(w.localStorage.getItem('caret.sidebarWidth'),null);
 assert.equal(w.document.body.style.getPropertyValue('--sidebar-width'),'210px');

 let latestScroll=null;$('messages').scrollTo=options=>{latestScroll=options;};
 Object.defineProperty($('messages'),'scrollHeight',{value:4000});
 $('chat-latest').click();assert.equal(latestScroll.top,4000);assert.equal(latestScroll.behavior,'smooth');
 assert.equal($('chat-latest').type,'button','Jumping to latest must not submit the prompt');
 assert.equal($('pdf-pane').hidden,false);assert.equal($('pdf-pages').children.length,3);
 let textLayer=$('pdf-pages').querySelector('.pdf-text-layer');assert.ok(textLayer);
 assert.equal(textLayer.textContent,'Hi\n\n');assert.equal(textLayer.querySelector('.pdf-text-char').style.left,'10%');
 $('pdf-scroll').getBoundingClientRect=()=>({left:0,top:0,right:600,bottom:800});
 w.Range.prototype.getClientRects=()=>[{left:60,top:100,right:72,bottom:112}];
 const copyRange=w.document.createRange();copyRange.selectNodeContents(textLayer);w.getSelection().removeAllRanges();w.getSelection().addRange(copyRange);
 $('pdf-scroll').dispatchEvent(new w.MouseEvent('mouseup',{bubbles:true}));
 assert.equal($('pdf-edit-selection').hidden,false);
 const liveMarks=$('pdf-pages').querySelectorAll('.pdf-selection-mark');
 assert.equal(liveMarks.length,1,'Adjacent glyphs are painted as one continuous row');
 assert.equal(liveMarks[0].style.left,'10%');assert.ok(Math.abs(parseFloat(liveMarks[0].style.width)-2)<1e-9);
 const liveOverlay=liveMarks[0].parentElement;
 for(let i=0;i<3;i++){w.document.dispatchEvent(new w.Event('selectionchange'));await tick();}
 assert.equal($('pdf-pages').querySelector('.pdf-selection-layer'),liveOverlay,'Unchanged selection keeps its overlay');
 assert.equal(liveOverlay.firstElementChild,liveMarks[0],'Repeated selection events must not rebuild marks');

 assert.equal($('pdf-edit-selection').parentElement,w.document.body);
 assert.equal($('pdf-edit-selection').style.top,'52px');
 assert.ok(parseFloat($('pdf-edit-selection').style.left)>=8);
 w.Range.prototype.getClientRects=()=>[{left:580,top:2,right:598,bottom:16}];
 w.dispatchEvent(new w.Event('resize'));
 assert.equal($('pdf-edit-selection').style.top,'24px','Near the top edge, the action moves below the selection');
 assert.ok(parseFloat($('pdf-edit-selection').style.left)+166<=600);
 w.document.dispatchEvent(new w.KeyboardEvent('keydown',{key:'Escape',bubbles:true}));
 assert.equal($('pdf-edit-selection').hidden,true);
 w.Range.prototype.getClientRects=()=>[{left:60,top:100,right:72,bottom:112}];
 $('pdf-scroll').dispatchEvent(new w.MouseEvent('mouseup',{bubbles:true}));

 w.eval("sections[0].input='Abstract draft';sections.push({id:'method',title:'Method',source_file:'main.tex',text:'Method text',versions:[{id:'m1'}],format:'latex'});selectedSection=1");
 $('prompt').value='Unsent Method question';
 // A feedback/card resize must not jump to the stale page-input value.
 const preview=$('pdf-scroll'),sheets=[...$('pdf-pages').children];
 const sheetHeight=()=>parseFloat($('pdf-pages').style.width)/100*(previewWidth-20)/.75;
 sheets.forEach((sheet,i)=>{sheet.getBoundingClientRect=()=>{const height=sheetHeight(),top=10+i*(height+12)-preview.scrollTop;return {top,bottom:top+height,height};};});
 preview.scrollTo=({top})=>{preview.scrollTop=top;};
 preview.scrollTop=10+sheetHeight()+12+150;
 $('pdf-page-input').value=1; // scroll events can lag behind text selection
 const readingPosition=preview.scrollTop;
 let promptFocusOptions;const originalFocus=$('prompt').focus.bind($('prompt'));
 $('prompt').focus=options=>{promptFocusOptions=options;originalFocus(options);};
 $('pdf-edit-selection').click();assert.equal($('pdf-feedback').hidden,true,'Selecting a passage must not show a transient progress banner');await tick();
 assert.equal($('pdf-feedback').hidden,true,'Successful selection must not show a transient success banner');resizePreview();await tick();
 assert.ok(Math.abs(preview.scrollTop-readingPosition)<.01,'Selecting a passage and resizing feedback must preserve the PDF position, not jump to the preceding page');
 assert.equal(promptFocusOptions?.preventScroll,true,'Composer focus must not scroll the document');
 const oldHeight=sheetHeight(),oldOffset=(preview.scrollTop-10-oldHeight-12)/oldHeight;
 previewHeight=500;resizePreview();await tick();
 assert.ok(Math.abs((preview.scrollTop-10-sheetHeight()-12)/sheetHeight()-oldOffset)<.001,'Automatic fitting preserves the same point within the visible page');
 sheets.forEach(sheet=>delete sheet.getBoundingClientRect);previewHeight=600;preview.scrollTop=0;
 $('prompt').focus=originalFocus;

 assert.equal($('pdf-pages').querySelector('.pdf-passage-layer'),liveOverlay,'Confirming the selected passage reuses the live overlay');
 assert.equal(liveOverlay.firstElementChild,liveMarks[0],'Equivalent server coordinates preserve the original highlight nodes');
 assert.equal(w.selectedSection,0,'Selecting a PDF passage switches to its section conversation');
 assert.equal(w.lastChatRender.id,'abstract');assert.equal(w.lastChatRender.latest,true);
 assert.equal($('prompt').value,'Abstract draft','Restore the destination conversation input');
 assert.equal(w.sections[1].input,'Unsent Method question','Preserve the previous conversation input');
 assert.equal($('tab-assistant').getAttribute('aria-selected'),'true');

 assert.equal($('passage-target').hidden,false);assert.match($('passage-target').textContent,/Original source/);
 assert.equal(w.eval('W.selectionRequest(selected()).text'),'Original source');
 await tick();assert.equal($('pdf-pages').querySelectorAll('.pdf-passage-mark').length,1);
 $('prompt').focus();w.getSelection().removeAllRanges();w.eval('renderSections()');
 assert.equal($('pdf-pages').querySelectorAll('.pdf-passage-mark').length,1,'Focusing the composer retains the highlight');
 w.eval('selected().paragraphTarget=JSON.parse(JSON.stringify(selected().paragraphTarget))');
 $('latex-preview').click();await tick();
 assert.equal($('pdf-pages').querySelectorAll('.pdf-passage-mark').length,1,'Reloading PDF DOM restores saved coordinates');
 w.eval("W.commit(selected(),'Revised source','revision');renderSections()");
 assert.equal($('pdf-pages').querySelectorAll('.pdf-passage-mark').length,1,'Adoption retains the highlight on the existing PDF');
 w.eval("latexInfo.compiled.runId='highlight-build';showLatexBuild()");await tick();await tick();
 assert.equal($('pdf-pages').querySelectorAll('.pdf-passage-mark').length,1,'Recompiled PDF remaps the highlight');
 assert.equal(w.eval('selected().paragraphTarget.pdfHighlight.runId'),'highlight-build');
 w.eval("selected().text='Original source';selected().versions=[{id:'v1'}];latexInfo.compiled.runId='build1';showLatexBuild()");await tick();

 w.eval('renderSections()');assert.equal($('passage-target').hidden,false,'Selection survives ordinary renders');
 $('passage-target').querySelector('button').click();await tick();assert.equal($('passage-target').hidden,true);assert.equal($('pdf-pages').querySelectorAll('.pdf-passage-mark').length,0);
 textLayer=$('pdf-pages').querySelector('.pdf-text-layer');copyRange.selectNodeContents(textLayer);w.getSelection().removeAllRanges();w.getSelection().addRange(copyRange);let copied;const copyEvent=new w.Event('copy',{bubbles:true,cancelable:true});Object.defineProperty(copyEvent,'clipboardData',{value:{setData:(type,text)=>{assert.equal(type,'text/plain');copied=text;}}});w.document.dispatchEvent(copyEvent);assert.equal(copied,'Hi\n\n');w.getSelection().removeAllRanges();
 assert.equal($('pdf-pages').children[0].style.aspectRatio,'600/800');
 assert.ok($('pdf-pages').querySelector('img').src.includes('workspaceId=one'));
 assert.equal(w.document.querySelector('main #workspace-tabs')!==null,true);
 assert.equal($('pdf-fit-page').getAttribute('aria-pressed'),'true');
 assert.ok(parseFloat($('pdf-pages').style.width)*previewWidth/100/(600/800)<=previewHeight-1.99,'Fit page must fit the available height');
 previewHeight=400;w.dispatchEvent(new w.Event('resize'));await tick();
 assert.ok(parseFloat($('pdf-pages').style.width)*previewWidth/100/(600/800)<=398.01,'Fit page must adapt to window resize');
 $('pdf-fit').click();
 $('pdf-zoom-in').click();assert.equal($('pdf-zoom-value').textContent,'110%');$('pdf-fit').click();assert.equal($('pdf-zoom-value').textContent,'100%');
 $('tab-source').click();await tick();assert.equal($('source-pane').hidden,false);assert.equal($('latex-source').value,'Original source');
 const pageImage=$('pdf-pages').querySelector('img');
 pageImage.getBoundingClientRect=()=>({left:10,top:20,width:300,height:400});
 textLayer.querySelector('.pdf-text-char').dispatchEvent(new w.MouseEvent('dblclick',{bubbles:true,clientX:160,clientY:220}));await tick();
 assert.equal($('source-pane').hidden,false);assert.equal($('latex-source').selectionStart,0);assert.equal($('latex-source').selectionEnd,'Original source'.length);
 const inverseUrl=new URL(w.requests.find(url=>url.includes('inverse-search')),w.location.href);
 assert.equal(inverseUrl.searchParams.get('x'),'300');assert.equal(inverseUrl.searchParams.get('y'),'400');assert.equal(inverseUrl.searchParams.get('page'),'1');assert.equal(inverseUrl.searchParams.get('v'),'build1');
 $('latex-source').value='Unsaved edit';$('latex-source').dispatchEvent(new w.Event('input'));
 const requestCount=w.requests.filter(url=>url.includes('inverse-search')).length;
 pageImage.dispatchEvent(new w.MouseEvent('dblclick',{bubbles:true,clientX:160,clientY:220}));await tick();
 assert.equal(w.requests.filter(url=>url.includes('inverse-search')).length,requestCount);
 assert.equal($('latex-source').value,'Unsaved edit');
 $('tab-assistant').click();$('tab-source').click();assert.equal($('latex-source').value,'Unsaved edit');
 await $('pdf-recompile').onclick();assert.equal(w.compileCount,0);assert.equal($('pdf-feedback').hidden,false);
 await $('latex-file-save').onclick();await $('pdf-recompile').onclick();await tick();assert.equal(w.compileCount,1);assert.ok($('pdf-pages').querySelector('img').src.includes('build2'));
 w.eval("latexInfo.lastBuild={ok:false,error:'Failed build'};showLatexBuild();");
 assert.equal($('pdf-pane').dataset.buildState,'failed');assert.equal($('pdf-pages').children.length,3);
 $('pdf-toggle').click();assert.equal($('pdf-pane').hidden,true);$('pdf-toggle').click();assert.equal($('pdf-pane').hidden,false);
 // Cmd+S saves dirty source first, recompiles once, and never submits chat.
 const cmdS=(extra={})=>{const e=new w.KeyboardEvent('keydown',{key:'s',metaKey:true,bubbles:true,cancelable:true,...extra});$('latex-source').dispatchEvent(e);return e;};
 const realSave=$('latex-file-save').onclick,realCompile=$('pdf-recompile').onclick;
 const actions=[];let finishSave;
 $('latex-file-save').onclick=async()=>{actions.push('save');await new Promise(resolve=>finishSave=resolve);w.latexOpenedFile.text=$('latex-source').value;return true;};
 $('pdf-recompile').onclick=async()=>{actions.push('compile');};
 $('latex-source').value='Shortcut source edit';
 assert.equal(cmdS().defaultPrevented,true);cmdS();cmdS({repeat:true});
 assert.deepEqual(actions,['save']);finishSave();await tick();assert.deepEqual(actions,['save','compile']);
 cmdS();await tick();assert.deepEqual(actions,['save','compile','compile'],'Clean source compiles directly');
 $('latex-source').value='Save will fail';$('latex-file-save').onclick=async()=>{actions.push('failed-save');return false;};
 cmdS();await tick();assert.equal(actions.at(-1),'failed-save');assert.equal($('latex-source').value,'Save will fail');
 const actionCount=actions.length;w.busy=true;cmdS();w.busy=false;w.latexCompiling=true;cmdS();w.latexCompiling=false;
 cmdS({isComposing:true});cmdS({keyCode:229});cmdS({repeat:true});cmdS({shiftKey:true});cmdS({metaKey:false});await tick();assert.equal(actions.length,actionCount);
 $('dialog').setAttribute('open','');cmdS();await tick();assert.equal(actions.length,actionCount);$('dialog').removeAttribute('open');
 // A project change during the awaited save must not compile the new project.
 $('latex-file-save').onclick=async()=>{w.project.id='changed-during-save';w.latexOpenedFile.text=$('latex-source').value;return true;};
 cmdS();await tick();assert.equal(actions.length,actionCount);w.project.id='one';
 $('latex-file-save').onclick=realSave;$('pdf-recompile').onclick=realCompile;
 // A compile in another tab can replace the PDF while lazy pages still load.
 // Recover the latest preview without reloading/discarding the source editor.
 const originalAPI=w.localAPI;let recoveryChecks=0;
 w.localAPI=async url=>{
   if(url.startsWith('/api/latex/info?')){recoveryChecks++;return {compiled:{runId:'fresh-build',sourceHash:'v1'},lastBuild:{ok:true}};}
   if(url.includes('pdf-text')&&url.includes('outdated'))throw new Error('PDF 已更新，请等待预览刷新后重试');
   return originalAPI(url);
 };
 $('latex-source').value='Keep my current edit';
 w.eval("latexInfo.compiled.runId='outdated';showLatexBuild();");await tick();
 await new Promise(r=>setTimeout(r,1150));
 assert.ok($('pdf-pages').querySelector('img').src.includes('fresh-build'));
 assert.equal($('pdf-pages').querySelectorAll('.pdf-text-layer').length,3);
 assert.equal($('latex-source').value,'Keep my current edit');
 assert.equal(recoveryChecks,1,'Concurrent failures should share the version refresh');
 assert.equal($('pdf-feedback').hidden,true);
 // A brief connection failure on an unchanged build should retry the text.
 let textAttempts=0;
 w.localAPI=async url=>{
   if(url.startsWith('/api/latex/info?'))return {compiled:{runId:'retry-build',sourceHash:'v1'},lastBuild:{ok:true}};
   if(url.includes('pdf-text')&&new URL(url,w.location.href).searchParams.get('page')==='1'&&textAttempts++===0)throw new Error('Temporary connection failure');
   return originalAPI(url);
 };
 w.eval("latexInfo.compiled.runId='retry-build';showLatexBuild();");await tick();
 await new Promise(r=>setTimeout(r,1150));
 assert.equal(textAttempts,2);assert.equal($('pdf-pages').querySelectorAll('.pdf-text-layer').length,3);
 w.localAPI=originalAPI;$('latex-source').value=w.latexOpenedFile.text;
 // Remote pages combine image/text, cap concurrency, and reuse exact-version
 // data when a preview is reopened; a new build must fetch fresh data.
 const bundles=[],pendingBundles=[];w.DraftRemote=true;
 w.localAPI=async url=>{
   if(url.startsWith('/api/remote/pdf-page?')){bundles.push(url);return new Promise(resolve=>pendingBundles.push(resolve));}
   return originalAPI(url);
 };
 const bundled={width:600,height:800,blocks:[[[['H',60,100,68,112]]]],image:'iVBORw0KGgo='};
 w.eval("latexInfo.compiled.runId='remote1';showLatexBuild();");await tick();
 assert.equal(bundles.length,2,'Only two remote pages may load concurrently');
 assert.equal(new URL(bundles[0],w.location.href).searchParams.get('page'),'1');
 pendingBundles.splice(0).forEach(resolve=>resolve(bundled));await tick();assert.equal(bundles.length,3);
 pendingBundles.splice(0).forEach(resolve=>resolve(bundled));await tick();
 assert.equal($('pdf-pages').querySelectorAll('.pdf-text-layer').length,3);
 assert.ok($('pdf-pages').querySelector('img').src.startsWith('data:image/png;base64,'));
 $('latex-preview').click();await tick();assert.equal(bundles.length,3,'Reopening the same build uses memory cache');
 w.eval("latexInfo.compiled.runId='remote2';showLatexBuild();");await tick();assert.equal(bundles.length,5);
 pendingBundles.splice(0).forEach(resolve=>resolve({...bundled}));await tick();
 pendingBundles.splice(0).forEach(resolve=>resolve({...bundled}));await tick();
 w.DraftRemote=false;w.localAPI=originalAPI;
 // A response from a previous project must never replace the newly selected project.
 let finish;w.pendingInfo=new Promise(r=>finish=r);
 w.eval("latexInfo.compiled.runId='build3';showLatexBuild();");await tick();await w.loadProject('two');
 finish({pages:7});await tick();assert.equal($('pdf-pages').children.length,0);assert.equal($('pdf-empty').hidden,false);
 // Unsaved files cannot be silently discarded on project switch.
 w.pendingInfo=null;$('tab-source').click();await tick();$('latex-source').value='Keep this';w.confirm=()=>false;
 await w.loadProject('three');assert.equal(w.project.id,'two');assert.equal($('latex-source').value,'Keep this');
 dom.window.close();console.log('PASS: split preview, zoom, source tabs, save guard, refreshed builds, failed builds, and project response isolation');
})().catch(e=>{dom.window.close();console.error(e);process.exitCode=1;});
