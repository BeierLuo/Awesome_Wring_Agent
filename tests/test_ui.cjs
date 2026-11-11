const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),path=require('node:path');
const root=path.resolve(__dirname,'..'),nodes=new Map();
function node(){return {value:'',textContent:'',hidden:false,disabled:false,options:[],children:[],listeners:{},classList:{add(){},remove(){}},removeAttribute(){},setAttribute(){},addEventListener(name,fn){(this.listeners[name]??=[]).push(fn)},append(...x){this.children.push(...x)},replaceChildren(...x){this.children=x;this.options=x},remove(){},scrollIntoView(){},showModal(){this.open=true},close(){this.open=false},setCustomValidity(){},reportValidity(){},focus(){}};}
let failExtractTitle=null,emptyExtractTitle=null,abortExtractTitle=null;
let saved=[],requests=[],revision=0,failure=false,answer='Approved revised abstract';
const response=data=>({ok:true,status:200,json:async()=>data});
const ctx={DraftMarkdown:{mount(el,text){el.textContent=text},render(el,text){el.textContent=text}},document:{getElementById:id=>{if(!nodes.has(id))nodes.set(id,node());return nodes.get(id)},querySelectorAll:()=>[],createElement:node},window:{addEventListener(){}},URL,Option:function(text,value){return {textContent:text,value}},AbortController,AbortSignal,DOMException,URLSearchParams,setTimeout,clearTimeout,Blob,TextDecoder,TextEncoder,ReadableStream,confirm:()=>true,console,navigator:{clipboard:{writeText:async()=>{}}}};
ctx.FileReader=class {readAsDataURL(blob){blob.arrayBuffer().then(data=>{this.result='data:application/pdf;base64,'+Buffer.from(data).toString('base64');this.onload();});}};
ctx.fetch=async(url,args)=>{
  if(url==='/api/workspaces')return response({root:'/tmp/test',items:[]});
  if(url.startsWith('/api/agent-files/context?')){const task=new URL('http://test'+url).searchParams.get('task');return response({instructions:fs.readFileSync(path.join(root,'agents/maintainer/AGENT.md'),'utf8')+'\n'+fs.readFileSync(path.join(root,'skills',task,'SKILL.md'),'utf8'),memory:{'preferences.md':'TEST_MEMORY_PREFERENCE'}});}
  const body=JSON.parse(args.body);requests.push({url,body});
  if(url==='/api/save'){saved.push(body);return response({revision:++revision,folder:'/tmp/test/paper'});}
  if(url==='/api/agent/run'){
    await new Promise(r=>setTimeout(r,1100));assert.match(nodes.get('agent-live').textContent,/总计 [1-9][0-9]*s/);assert.equal(body.revision,revision,'Typing autosave must not change the revision while starting a writing run');
    const event=failure?{type:'error',error:'quota test'}:{type:'result',answer,provider:body.config.writer_provider,model:body.config.writer_provider==='gcp'?'gemini-4-argon':'test',finishReason:'STOP',baseVersion:null,runId:body.runId,trace:[],usage:{promptTokenCount:80},context:{default:'current_section_only',pdfPages:[]},modelCalls:1};
    const bytes=new TextEncoder().encode(JSON.stringify({type:'progress',message:'只读取当前章节'})+'\n'+JSON.stringify({type:'activity',message:'开始：读取 hongxin · abstract',elapsed:0.2})+'\n'+JSON.stringify({type:'writer_start',round:1})+'\n'+JSON.stringify({type:'writer_delta',round:1,text:'Visible partial answer'})+'\n'+JSON.stringify(event)+'\n');let i=0;
    return {ok:true,body:new ReadableStream({pull(controller){if(i>=bytes.length){assert.match(nodes.get('agent-output-text').textContent,/Visible partial answer/);controller.close();}else{controller.enqueue(bytes.slice(i,i+7));i+=7;}}})};
  }
  if(url==='/api/paper/context')return response(body.mode==='outline'?{page_count:3,page_candidates:[{page:1,headings:['Abstract'],needs_image:false}]}:{pages:[{page:body.start_page,text:'ONLY_SELECTED_PAGE'}],images:[]});
  if(url.includes('openai.com')){
    const input=body.input[0].content[0].text;let payload;try{payload=JSON.parse(input)}catch{}
    if(payload?.title===failExtractTitle&&failExtractTitle)throw new Error('temporary extraction failure');
    if(payload?.title===abortExtractTitle&&abortExtractTitle)vm.runInContext('controller.abort()',ctx);
    const parsed=body.instructions.includes('Identify top-level sections')?{sections:[{title:'Abstract',start_page:1,end_page:1},{title:'Method',start_page:2,end_page:3}],notes:''}:{text:payload?.title===emptyExtractTitle&&emptyExtractTitle?'':'Approved revised abstract',notes:'Test extraction'};
    return response({status:'completed',output:[{content:[{type:'output_text',text:JSON.stringify(parsed)}]}]});
  }
  throw new Error('Unexpected API '+url);
};
vm.createContext(ctx);for(const match of fs.readFileSync(path.join(root,'ui/index.html'),'utf8').matchAll(/id="([^"]+)"/g))ctx.document.getElementById(match[1]);
for(const file of ['app.js','workspace-core.js','providers.js','workspace.js'])vm.runInContext(fs.readFileSync(path.join(root,'ui',file),'utf8'),ctx);
(async()=>{
  await new Promise(r=>setImmediate(r));await vm.runInContext('createProject()',ctx);
  const traceEntry=vm.runInContext("renderEntry({role:'model',text:'Visible answer',canAdopt:false,agent:{trace:[{tool:'read_style_memory',status:'ok',author:'hongxin',section:'abstract'}]}})",ctx);
  const traceIndex=traceEntry.children.findIndex(e=>e.className==='reading-trace');
  const bodyIndex=traceEntry.children.findIndex(e=>e.className==='body');
  assert.ok(traceIndex>=0&&traceIndex<bodyIndex,'Execution trace must precede the answer');
  assert.equal(traceEntry.children[traceIndex].open,true);
  assert.match(traceEntry.children[traceIndex].children[0].textContent,/read_style_memory/);

  vm.runInContext("sections=[W.makeSection({title:'Abstract',start_page:1,end_page:1},0),W.makeSection({title:'Method',start_page:2,end_page:3},1)];W.commit(sections[0],'Original abstract','extract');W.commit(sections[1],'Latest method','extract');project.sections=sections;selectedSection=0;renderSections();pdf={name:'fixture.pdf',data:'FULL_PDF_MUST_NOT_BE_SENT',blob:{size:123}};",ctx);
  nodes.get('writer-provider').value='gemini';nodes.get('key').value='GEMINI_TEST_SECRET';nodes.get('model').value='models/test';nodes.get('openai-key').value='OPENAI_TEST_SECRET';nodes.get('openai-model').value='test';nodes.get('prompt').value='polish';
  for(const listener of nodes.get('prompt').listeners.input||[])listener();
  await nodes.get('form').onsubmit({preventDefault(){}});
  assert.equal(vm.runInContext('sections[0].chat.length',ctx),2);assert.equal(vm.runInContext('sections[0].text',ctx),'Original abstract');
  const request=requests.find(r=>r.url==='/api/agent/run');assert.equal(request.body.prompt,'polish');assert.ok(request.body.sectionId);assert.equal(request.body.revision,2);assert.ok(!('contents'in request.body));assert.ok(!JSON.stringify(request).includes('Latest method'));assert.ok(!JSON.stringify(request).includes('FULL_PDF'));
  await vm.runInContext('prepareProposal(sections[0].chat[1])',ctx);assert.equal(vm.runInContext('sections[0].text',ctx),'Original abstract');assert.ok(nodes.get('proposal-dialog').open);
  await nodes.get('accept-proposal').onclick();assert.equal(vm.runInContext('sections[0].text',ctx),'Approved revised abstract');assert.equal(vm.runInContext('sections[0].versions.length',ctx),2);
  vm.runInContext('selectedSection=1;renderSections();renderChat();',ctx);nodes.get('writer-provider').value='gcp';nodes.get('gcp-auth').value='express';nodes.get('gcp-key').value='GCP_TEST_SECRET';nodes.get('gcp-model').value='gemini-4-argon';nodes.get('prompt').value='review method';
  await nodes.get('form').onsubmit({preventDefault(){}});assert.equal(vm.runInContext('sections[1].chat.at(-1).provider',ctx),'gcp');assert.equal(vm.runInContext('sections[0].chat.length',ctx),2);
  failure=true;nodes.get('prompt').value='retry later';await nodes.get('form').onsubmit({preventDefault(){}});assert.equal(nodes.get('prompt').value,'retry later');assert.equal(vm.runInContext('sections[1].chat.length',ctx),2);failure=false;
  assert.equal(nodes.get('agent-activity').hidden,false);assert.equal(nodes.get('agent-activity').open,true);assert.match(nodes.get('agent-events').textContent,/hongxin/);assert.match(nodes.get('agent-events').textContent,/quota test/);
  vm.runInContext('selectedSection=0;renderChat()',ctx);assert.ok(!nodes.get('agent-events').textContent.includes('quota test'));
  vm.runInContext('selectedSection=1;renderChat()',ctx);assert.match(nodes.get('agent-events').textContent,/quota test/);
  vm.runInContext('sections[1].initialized=false;sections[1].text="";',ctx);await vm.runInContext('extractDraft(sections[1],new AbortController().signal)',ctx);
  const extraction=requests.filter(r=>r.url.includes('openai.com')).at(-1);assert.match(extraction.body.input[0].content[0].text,/ONLY_SELECTED_PAGE/);assert.ok(!JSON.stringify(extraction).includes('FULL_PDF'));assert.ok(!JSON.stringify(extraction).includes('input_file'));
  assert.equal(JSON.stringify(saved).includes('TEST_SECRET'),false);assert.equal(requests.some(r=>r.url.includes('/upload/')),false);
  // Import preparation persists completed sections and resumes without overwriting them.
  vm.runInContext("sections=[W.makeSection({title:'Existing',start_page:1,end_page:1},0),W.makeSection({title:'New A',start_page:2,end_page:2},1),W.makeSection({title:'New B',start_page:3,end_page:3},2)];W.commit(sections[0],'USER EDIT MUST SURVIVE','manual');project.sections=sections;selectedSection=-1;",ctx);
  failExtractTitle='New B';await vm.runInContext('prepareAllSections()',ctx);
  assert.equal(vm.runInContext('sections[1].initialized',ctx),true);assert.equal(vm.runInContext('sections[2].initialized',ctx),false);assert.match(nodes.get('split').textContent,/继续/);
  assert.equal(saved.at(-1).state.sections[1].initialized,true);
  const readyVersions=vm.runInContext('sections[1].versions.length',ctx);
  failExtractTitle=null;await vm.runInContext('prepareAllSections()',ctx);
  assert.equal(vm.runInContext('sections.every(s=>s.initialized)',ctx),true);assert.equal(vm.runInContext('sections[0].text',ctx),'USER EDIT MUST SURVIVE');assert.equal(vm.runInContext('sections[1].versions.length',ctx),readyVersions);
  vm.runInContext("sections=[W.makeSection({title:'Empty',start_page:1,end_page:1},0)];project.sections=sections;",ctx);
  emptyExtractTitle='Empty';await vm.runInContext('prepareAllSections()',ctx);assert.equal(vm.runInContext('sections[0].initialized',ctx),false);emptyExtractTitle=null;
  abortExtractTitle='Empty';await vm.runInContext('prepareAllSections()',ctx);assert.equal(vm.runInContext('sections[0].initialized',ctx),false);abortExtractTitle=null;
  vm.runInContext('sections=[];project.sections=sections;',ctx);await vm.runInContext('prepareAllSections()',ctx);
  assert.equal(vm.runInContext('sections.length',ctx),2);assert.equal(vm.runInContext('sections.every(s=>s.initialized)',ctx),true);
  assert.equal(vm.runInContext('busy',ctx),false);
  await vm.runInContext('createProject()',ctx);
  ctx.testUpload=new Blob(['%PDF-1.7 fake local fixture']);ctx.testUpload.name='uploaded-paper.pdf';
  await vm.runInContext('attach(testUpload)',ctx);
  assert.equal(vm.runInContext('project.pdfName',ctx),'uploaded-paper.pdf');assert.equal(vm.runInContext('sections.length',ctx),2);assert.equal(vm.runInContext('sections.every(s=>s.initialized)',ctx),true);
  assert.ok(saved.some(r=>r.pdfData),'PDF saved locally before automatic extraction');
  const W=require(path.join(root,'ui/workspace-core.js'));const a=W.makeSection({title:'A'},0),b=W.makeSection({title:'B'},1);W.commit(a,'only-current','initial');W.commit(b,'other-section-secret','initial');assert.ok(!W.context([a,b],a).includes('other-section-secret'));a.pending=W.proposal(a,'new','id');W.commit(a,'manual','manual');assert.throws(()=>W.accept(a),/已变化/);
  // LaTeX adoption is local, keyless, version-bound and explicitly reviewed.
  nodes.get('openai-key').value='';
  vm.runInContext("sections=[W.makeSection({title:'Method'},0)];project.sections=sections;selectedSection=0;sections[0].format='latex';sections[0].source_file='sections/method.tex';W.commit(sections[0],String.raw`\\section{Method}\nOld $x=1$ and \\cite{key}.`,'import');",ctx);
  ctx.latexAnswer='```latex\n\\section{Method}\nNew $x=1$ and \\cite{key}.\n```\n保留公式与引用。';
  vm.runInContext("sections[0].chat=[{id:'latex-response',role:'model',text:latexAnswer,canAdopt:true,baseVersion:sections[0].versions.at(-1).id}];",ctx);
  const requestCount=requests.length;
  await vm.runInContext('prepareProposal(sections[0].chat[0])',ctx);
  assert.ok(nodes.get('proposal-dialog').open);
  assert.match(vm.runInContext('sections[0].text',ctx),/Old/);
  assert.equal(vm.runInContext('sections[0].pending.text',ctx),'\\section{Method}\nNew $x=1$ and \\cite{key}.\n');
  assert.ok(requests.slice(requestCount).every(r=>r.url==='/api/save'),'No model or PDF request when preparing LaTeX');
  await nodes.get('accept-proposal').onclick();
  assert.match(vm.runInContext('sections[0].text',ctx),/New/);
  assert.equal(vm.runInContext('sections[0].versions.at(-1).reason',ctx),'采用 Gemini LaTeX 修改');
  assert.throws(()=>vm.runInContext('W.latexRevision(sections[0],sections[0].chat[0])',ctx),/当前版本/);
  // Direct adoption saves the clicked reply without opening review or calling a model.
  vm.runInContext("sections[0].chat.push({id:'direct-response',role:'model',text:latexAnswer.replace('New','Direct'),canAdopt:true,baseVersion:sections[0].versions.at(-1).id})",ctx);
  const directEntry=vm.runInContext('renderEntry(sections[0].chat.at(-1))',ctx);
  const reviewIndex=directEntry.children.findIndex(n=>n.textContent==='查看 LaTeX 修改稿');
  const directButton=directEntry.children[reviewIndex+1];
  assert.equal(directButton.textContent,'采用当前 LaTeX 修改稿');
  const directRequestCount=requests.length;
  await directButton.onclick();
  assert.equal(nodes.get('proposal-dialog').open,false);
  assert.match(saved.at(-1).state.sections[0].text,/Direct/);
  assert.equal(vm.runInContext('sections[0].versions.length',ctx),3);
  assert.equal(vm.runInContext('sections[0].pending',ctx),null);
  assert.equal(requests.length,directRequestCount+1);
  assert.equal(requests.at(-1).url,'/api/save');
  await directButton.onclick();
  assert.equal(requests.length,directRequestCount+1,'Stale reply must not write again');
  assert.match(nodes.get('status').textContent,/当前版本/);
  const unfinished=vm.runInContext("renderEntry({...sections[0].chat.at(-1),canAdopt:false})",ctx);
  const disabledAdopt=unfinished.children.find(n=>n.textContent==='采用当前 LaTeX 修改稿');
  assert.equal(disabledAdopt.disabled,true);
  await disabledAdopt.onclick();
  assert.equal(requests.length,directRequestCount+1);
  for(const invalid of ['Discuss only','```latex\nA\n```\n```tex\nB\n```','```latex\nunfinished']){
    ctx.invalid=invalid;
    assert.throws(()=>vm.runInContext('W.latexRevision(sections[0],{text:invalid,baseVersion:sections[0].versions.at(-1).id})',ctx),/完整的 LaTeX/);
  }
  vm.runInContext('sections[0].pending=W.proposal(sections[0],"pending","reply");W.commit(sections[0],"manual edit","manual");',ctx);
  assert.throws(()=>vm.runInContext('W.accept(sections[0])',ctx),/已变化/);
  console.log('PASS: agent streaming, PDF import/extraction/adoption, source-only LaTeX review without GPT, exact source text, stale-reply and ambiguous-code protection.');
})().catch(e=>{console.error(e);process.exitCode=1});
