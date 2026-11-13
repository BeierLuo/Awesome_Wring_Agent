const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {JSDOM}=require('jsdom');const root=path.resolve(__dirname,'..');
async function scenario(lang){
 const dom=new JSDOM(fs.readFileSync(path.join(root,'ui/index.html'),'utf8'),{url:'http://127.0.0.1:8768/',runScripts:'outside-only'}),w=dom.window;
 w.document.documentElement.lang=lang;w.HTMLDialogElement.prototype.showModal=function(){this.open=true;};w.HTMLDialogElement.prototype.close=function(){this.open=false;};
 const requests=[];let connected=false;
 w.eval(`var $=id=>document.getElementById(id),project={id:'paper',latex:{}},busy=false,latexCompiling=false,inputTimer,latexOpenedFile=null,dirty=false;function setBusy(value){busy=value;}function renderLatexProject(){}function fileDirty(){return dirty;}function localStatus(text){$('status').textContent=text;}async function persist(){return true;}async function loadProject(id){if(id!=='paper')throw Error('Wrong project');}`);
 w.localAPI=async(url,options)=>{
   const body=JSON.parse(options.body);requests.push({url,body});assert.equal(options.headers['X-Draft-Overleaf'],'1');
   const status=()=>({connected,url:connected?'https://git@git.overleaf.com/abcdef':'',hasToken:connected});
   if(url.endsWith('/status'))return status();
   if(url.endsWith('/connect')){connected=true;return status();}
   if(url.endsWith('/preview'))return {previewId:'ticket',direction:body.direction,status:status(),skipped:[],changes:[{path:'main.tex',kind:'conflict',diff:'<img src=x onerror=alert(1)>'}]};
   if(url.endsWith('/apply')){assert.equal(body.previewId,'ticket');assert.equal(body.resolutions['main.tex'],'remote');return {status:status(),changed:true};}
   if(url.endsWith('/disconnect')){connected=false;return status();}
   throw Error(url);
 };
 w.eval(fs.readFileSync(path.join(root,'ui/overleaf.js'),'utf8'));
 const $=id=>w.document.getElementById(id);
 await $('overleaf-open').onclick();assert.ok($('overleaf-dialog').open);assert.ok($('overleaf-pull').disabled);
 $('overleaf-url').value='https://www.overleaf.com/project/abcdef';$('overleaf-token').value='DUMMY_TOKEN';await $('overleaf-connect').onclick();
 assert.equal($('overleaf-token').value,'');assert.equal($('overleaf-pull').disabled,false);
 await $('overleaf-pull').onclick();assert.ok($('overleaf-apply').disabled);assert.equal($('overleaf-changes').querySelectorAll('img').length,0);
 const select=$('overleaf-changes').querySelector('select');select.value='remote';select.onchange();assert.equal($('overleaf-apply').disabled,false);
 await $('overleaf-apply').onclick();assert.equal($('overleaf-review').hidden,true);
 assert.ok(!JSON.stringify(requests.filter(r=>!r.url.endsWith('/connect'))).includes('DUMMY_TOKEN'));
 if(lang==='en')assert.ok(!/[\u4e00-\u9fff]/.test($('overleaf-dialog').textContent));
 await $('overleaf-disconnect').onclick();assert.ok($('overleaf-push').disabled);
 $('overleaf-close').onclick();w.dirty=true;const count=requests.length;await $('overleaf-open').onclick();assert.equal(requests.length,count);
 dom.window.close();
}
(async()=>{await scenario('zh-CN');await scenario('en');console.log('PASS: Overleaf connection, preview, conflict choices, source guard and bilingual UI');})().catch(e=>{console.error(e);process.exitCode=1;});
