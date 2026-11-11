const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {JSDOM}=require('jsdom');
const root=path.resolve(__dirname,'..');
const dom=new JSDOM(fs.readFileSync(path.join(root,'ui/index.html'),'utf8'),{runScripts:'outside-only',url:'http://127.0.0.1:8769/',pretendToBeVisual:true});
const w=dom.window;w.confirm=()=>true;
w.HTMLElement.prototype.scrollTo=function(){};
w.eval(`
var $=id=>document.getElementById(id),busy=false,latexCompiling=false,inputTimer;
var project={id:'one',latex:{main:'main.tex',sourceHash:'v1',files:[{path:'main.tex',editable:true,size:50}]}},sections=[];
var latexInfo={workspaceId:'one',compiled:{runId:'build1',sourceHash:'v1'},lastBuild:{ok:true}};
var latexOpenedFile=null,latexFileRevision=0,compileCount=0,requests=[],pendingInfo=null;
function selected(){return {title:'Abstract',source_file:'main.tex',text:'Original source'};}
function fileDirty(){return latexOpenedFile&&$('latex-source').value!==latexOpenedFile.text;}
function renderLatexProject(){} function showLatexBuild(){} function renderSections(){}
async function persist(){return true;}
async function loadProject(id){project={id,latex:{main:'main.tex',sourceHash:'v1',files:[{path:'main.tex',editable:true,size:50}]}};latexInfo=null;renderLatexProject();}
async function localAPI(url){requests.push(url);if(url.includes('pdf-info')){if(pendingInfo)return pendingInfo;return {pages:3,sizes:[[600,800],[600,800],[600,800]]};}return {path:'main.tex',text:'Original source',revision:1,sha256:'abc'};}
$('latex-file-save').onclick=async()=>{latexOpenedFile.text=$('latex-source').value;};
$('draft-edit').onclick=()=>{};
$('latex-compile').onclick=async()=>{compileCount++;latexInfo={workspaceId:project.id,compiled:{runId:'build2',sourceHash:'v1'},lastBuild:{ok:true}};showLatexBuild();};
`);
assert.equal(w.document.getElementById('workspace-topbar').hidden,true,'Uninitialized layout must not appear alongside the old workspace');
assert.equal(w.document.getElementById('workspace-tabs').hidden,true);
let previewWidth=800,previewHeight=600;
Object.defineProperty(w.document.getElementById('pdf-scroll'),'clientWidth',{get:()=>previewWidth});
Object.defineProperty(w.document.getElementById('pdf-scroll'),'clientHeight',{get:()=>previewHeight});
w.eval(fs.readFileSync(path.join(root,'ui/split-workspace.js'),'utf8'));
const tick=()=>new Promise(r=>setTimeout(r,30));
(async()=>{
 await tick();const $=id=>w.document.getElementById(id);
 assert.equal($('workspace-topbar').hidden,false);assert.equal($('workspace-tabs').hidden,false);
 assert.equal($('pdf-pane').hidden,false);assert.equal($('pdf-pages').children.length,3);
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
 $('latex-source').value='Unsaved edit';$('latex-source').dispatchEvent(new w.Event('input'));
 $('tab-assistant').click();$('tab-source').click();assert.equal($('latex-source').value,'Unsaved edit');
 await $('pdf-recompile').onclick();assert.equal(w.compileCount,0);assert.equal($('pdf-feedback').hidden,false);
 await $('latex-file-save').onclick();await $('pdf-recompile').onclick();await tick();assert.equal(w.compileCount,1);assert.ok($('pdf-pages').querySelector('img').src.includes('build2'));
 w.eval("latexInfo.lastBuild={ok:false,error:'Failed build'};showLatexBuild();");
 assert.equal($('pdf-pane').dataset.buildState,'failed');assert.equal($('pdf-pages').children.length,3);
 $('pdf-toggle').click();assert.equal($('pdf-pane').hidden,true);$('pdf-toggle').click();assert.equal($('pdf-pane').hidden,false);
 // A response from a previous project must never replace the newly selected project.
 let finish;w.pendingInfo=new Promise(r=>finish=r);
 w.eval("latexInfo.compiled.runId='build3';showLatexBuild();");await tick();await w.loadProject('two');
 finish({pages:7});await tick();assert.equal($('pdf-pages').children.length,0);assert.equal($('pdf-empty').hidden,false);
 // Unsaved files cannot be silently discarded on project switch.
 w.pendingInfo=null;$('tab-source').click();await tick();$('latex-source').value='Keep this';w.confirm=()=>false;
 await w.loadProject('three');assert.equal(w.project.id,'two');assert.equal($('latex-source').value,'Keep this');
 dom.window.close();console.log('PASS: split preview, zoom, source tabs, save guard, refreshed builds, failed builds, and project response isolation');
})().catch(e=>{dom.window.close();console.error(e);process.exitCode=1;});
