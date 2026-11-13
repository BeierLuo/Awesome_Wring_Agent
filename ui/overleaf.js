'use strict';
(() => {
  const t=(en,zh)=>document.documentElement.lang==='en'?en:zh;
  const button=document.createElement('button');button.id='overleaf-open';button.type='button';button.textContent=t('Overleaf sync','Overleaf \u540c\u6b65');
  $('workspace-tabs').insertBefore(button,$('pdf-toggle'));
  const dialog=document.createElement('dialog');dialog.id='overleaf-dialog';
  dialog.innerHTML='<div class="dialog-top"><strong>Overleaf</strong><button id="overleaf-close" type="button"></button></div><p id="overleaf-help"></p><label for="overleaf-url" id="overleaf-url-label"></label><input id="overleaf-url" type="url" placeholder="https://git.overleaf.com/…" autocomplete="off"><label for="overleaf-token" id="overleaf-token-label"></label><input id="overleaf-token" type="password" autocomplete="new-password"><small id="overleaf-private"></small><div class="overleaf-actions"><button id="overleaf-connect" type="button"></button><button id="overleaf-disconnect" type="button"></button><a id="overleaf-token-link" href="https://www.overleaf.com/user/settings" target="_blank" rel="noopener"></a></div><p id="overleaf-connection"></p><div class="overleaf-actions"><button id="overleaf-pull" type="button"></button><button id="overleaf-push" type="button"></button></div><p id="overleaf-status" role="status"></p><div id="overleaf-review" hidden><p id="overleaf-review-note"></p><div id="overleaf-changes"></div><p id="overleaf-skipped"></p><button id="overleaf-apply" class="primary" type="button"></button></div>';
  document.body.append(dialog);
  $('overleaf-close').textContent=t('Close','\u5173\u95ed');
  $('overleaf-help').textContent=t('Connect this local LaTeX project to Overleaf Cloud. Preview changes before pulling or pushing. Git access is required.','\u5c06\u5f53\u524d\u672c\u5730 LaTeX \u9879\u76ee\u8fde\u63a5\u5230 Overleaf Cloud。\u83b7\u53d6\u6216\u63a8\u9001\u524d\u5148\u9884\u89c8\u53d8\u5316，\u9700\u8981 Overleaf Git \u6743\u9650。');
  $('overleaf-url-label').textContent=t('Overleaf project or Git URL','Overleaf \u9879\u76ee\u6216 Git \u5730\u5740');
  $('overleaf-token-label').textContent=t('Git access token','Git \u8bbf\u95ee\u4ee4\u724c');
  $('overleaf-private').textContent=t('The token is stored on this computer with owner-only permissions, outside paper backups. Only paper source files and assets are synced; chat, API settings and project memory stay local.','\u4ee4\u724c\u4ec5\u4fdd\u5b58\u5728\u672c\u673a，\u4ec5\u5f53\u524d\u7cfb\u7edf\u7528\u6237\u53ef\u8bfb\u5199，\u4e0d\u8fdb\u5165\u8bba\u6587\u5907\u4efd。\u540c\u6b65\u4ec5\u5305\u542b\u8bba\u6587\u6e90\u6587\u4ef6\u548c\u8d44\u6e90，\u5bf9\u8bdd、API \u914d\u7f6e\u548c\u9879\u76ee\u8bb0\u5fc6\u7559\u5728\u672c\u5730。');
  $('overleaf-connect').textContent=t('Connect / update token','\u8fde\u63a5 / \u66f4\u65b0\u4ee4\u724c');
  $('overleaf-disconnect').textContent=t('Disconnect','\u65ad\u5f00\u8fde\u63a5');
  $('overleaf-token-link').textContent=t('Get a token','\u83b7\u53d6\u4ee4\u724c');
  $('overleaf-pull').textContent=t('Preview pull from Overleaf','\u9884\u89c8\u83b7\u53d6 Overleaf \u4fee\u6539');
  $('overleaf-push').textContent=t('Preview push to Overleaf','\u9884\u89c8\u63a8\u9001\u5230 Overleaf');
  let connection={},preview=null,working=false,workspaceId=null;
  const notice=text=>{$('overleaf-status').textContent=text;};
  function controls(){
    for(const node of dialog.querySelectorAll('button,input,select'))node.disabled=working;
    const connected=!!connection.connected;
    $('overleaf-disconnect').hidden=!connected;
    $('overleaf-pull').disabled=$('overleaf-push').disabled=working||!connected||$('overleaf-url').value!==connection.url;
    $('overleaf-token').placeholder=connection.hasToken?t('Leave blank to keep the saved token','\u7559\u7a7a\u4fdd\u7559\u5df2\u4fdd\u5b58\u7684\u4ee4\u724c'):'';
    $('overleaf-connection').textContent=connected?t('Connected','\u5df2\u8fde\u63a5')+(connection.lastSync?' · '+t('Last sync: ','\u4e0a\u6b21\u540c\u6b65：')+new Date(connection.lastSync).toLocaleString():''):t('Not connected','\u672a\u8fde\u63a5');
    const unresolved=[...dialog.querySelectorAll('[data-conflict]')].some(select=>!select.value);
    $('overleaf-apply').disabled=working||!preview||unresolved;
  }
  function invalidate(){preview=null;$('overleaf-review').hidden=true;controls();}
  const request=(action,data={})=>localAPI('/api/overleaf/'+action,{method:'POST',headers:{'Content-Type':'application/json','X-Draft-Overleaf':'1'},body:JSON.stringify({workspaceId,...data})});
  async function run(fn){
    if(working)return;working=true;setBusy(true);$('send').disabled=true;controls();
    try{await fn();}catch(error){notice(error.message);invalidate();}
    finally{working=false;setBusy(false);controls();}
  }
  const oldRender=renderLatexProject;renderLatexProject=function(){oldRender();button.hidden=!project?.latex;button.disabled=busy||latexCompiling;};
  renderLatexProject();
  button.onclick=async()=>{
    if(busy||!project?.latex)return;
    if(fileDirty()){localStatus(t('Save source edits before syncing.','\u8bf7\u5148\u4fdd\u5b58\u6e90\u7801\u7f16\u8f91，\u518d\u540c\u6b65。'));return;}
    workspaceId=project.id;connection={};$('overleaf-url').value='';$('overleaf-token').value='';invalidate();dialog.showModal();
    await run(async()=>{clearTimeout(inputTimer);if(!await persist())throw new Error(t('Save the project before syncing.','\u8bf7\u5148\u6210\u529f\u4fdd\u5b58\u9879\u76ee。'));connection=await request('status');$('overleaf-url').value=connection.url;notice('');});
  };
  const close=()=>{if(!working){$('overleaf-token').value='';invalidate();dialog.close();}};
  $('overleaf-close').onclick=close;dialog.addEventListener('cancel',event=>{event.preventDefault();close();});
  $('overleaf-url').oninput=()=>invalidate();$('overleaf-token').oninput=()=>invalidate();
  $('overleaf-connect').onclick=()=>run(async()=>{
    notice(t('Checking Overleaf access…','\u6b63\u5728\u68c0\u67e5 Overleaf \u8fde\u63a5…'));invalidate();
    const token=$('overleaf-token').value;
    try{connection=await request('connect',{url:$('overleaf-url').value,token});$('overleaf-url').value=connection.url;notice(t('Connected. Preview a pull or push to compare both projects.','\u5df2\u8fde\u63a5。\u8bf7\u9884\u89c8\u83b7\u53d6\u6216\u63a8\u9001，\u6838\u5bf9\u53cc\u65b9\u6587\u4ef6。'));}
    finally{$('overleaf-token').value='';}
  });
  $('overleaf-disconnect').onclick=()=>run(async()=>{connection=await request('disconnect');invalidate();notice(t('Disconnected. Local and Overleaf files are unchanged.','\u5df2\u65ad\u5f00\u8fde\u63a5，\u672c\u5730\u548c Overleaf \u6587\u4ef6\u4fdd\u6301\u4e0d\u53d8。'));});
  async function showPreview(direction){await run(async()=>{
    invalidate();notice(t('Checking both projects…','\u6b63\u5728\u6bd4\u8f83\u53cc\u65b9\u9879\u76ee…'));
    preview=await request('preview',{direction});connection=preview.status;
    $('overleaf-review-note').textContent=(direction==='pull'?t('Apply remote changes locally; keep local-only edits.','\u83b7\u53d6\u8fdc\u7aef\u4fee\u6539\u5230\u672c\u5730，\u4fdd\u7559\u4ec5\u5728\u672c\u5730\u53d1\u751f\u7684\u4fee\u6539。'):t('Merge changes from both sides and publish the result to Overleaf.','\u5408\u5e76\u53cc\u65b9\u4fee\u6539，\u5e76\u5c06\u7ed3\u679c\u63a8\u9001\u5230 Overleaf。'))+' '+t('For conflicts, choose which entire file to keep. Diff: − local, + Overleaf (excerpt).','\u9047\u5230\u51b2\u7a81，\u8bf7\u9009\u62e9\u4fdd\u7559\u54ea\u4e00\u65b9\u7684\u5b8c\u6574\u6587\u4ef6。\u5dee\u5f02：− \u672c\u5730，+ Overleaf（\u8282\u9009）。');
    const rows=$('overleaf-changes');rows.replaceChildren();
    for(const change of preview.changes){
      const item=document.createElement('details');item.open=change.kind==='conflict';
      const label=document.createElement('summary');label.textContent=change.path+' · '+({local:t('Local change','\u672c\u5730\u4fee\u6539'),remote:t('Overleaf change','Overleaf \u4fee\u6539'),conflict:t('Conflict — choose a version','\u51b2\u7a81 — \u8bf7\u9009\u62e9\u7248\u672c')}[change.kind]);item.append(label);
      if(change.kind==='conflict'){
        const select=document.createElement('select');select.dataset.conflict=change.path;select.setAttribute('aria-label',change.path);
        select.append(new Option(t('Choose a version…','\u9009\u62e9\u4fdd\u7559\u7248\u672c…'),''),new Option(change.localDeleted?t('Keep local deletion','\u91c7\u7528\u672c\u5730\u5220\u9664'):t('Keep local file','\u4fdd\u7559\u672c\u5730\u6587\u4ef6'),'local'),new Option(change.remoteDeleted?t('Keep Overleaf deletion','\u91c7\u7528 Overleaf \u5220\u9664'):t('Keep Overleaf file','\u4fdd\u7559 Overleaf \u6587\u4ef6'),'remote'));
        select.onchange=controls;item.append(select);
      }
      if(change.localDeleted||change.remoteDeleted){const info=document.createElement('p');info.textContent=change.localDeleted?t('File is absent locally.','\u672c\u5730\u6ca1\u6709\u6b64\u6587\u4ef6。'):t('File is absent on Overleaf.','Overleaf \u6ca1\u6709\u6b64\u6587\u4ef6。');item.append(info);}
      if(change.diff){const pre=document.createElement('pre');pre.textContent=change.diff;item.append(pre);}rows.append(item);
    }
    $('overleaf-skipped').textContent=preview.skipped.length?t('Unsupported files stay on Overleaf: ','\u672a\u652f\u6301\u7684\u6587\u4ef6\u4fdd\u7559\u5728 Overleaf：')+preview.skipped.join(', '):'';
    $('overleaf-apply').textContent=direction==='pull'?t('Apply to local project','\u786e\u8ba4\u66f4\u65b0\u672c\u5730\u9879\u76ee'):t('Sync to Overleaf','\u786e\u8ba4\u540c\u6b65\u5230 Overleaf');
    $('overleaf-review').hidden=false;notice(preview.changes.length?t('Review the changes below.','\u8bf7\u6838\u5bf9\u4e0b\u65b9\u4fee\u6539。'):t('Files match. Confirm to record this sync point.','\u6587\u4ef6\u4e00\u81f4。\u53ef\u786e\u8ba4\u8bb0\u5f55\u540c\u6b65\u72b6\u6001。'));
  });}
  $('overleaf-pull').onclick=()=>showPreview('pull');$('overleaf-push').onclick=()=>showPreview('push');
  $('overleaf-apply').onclick=()=>run(async()=>{
    const resolutions={};for(const select of dialog.querySelectorAll('[data-conflict]'))resolutions[select.dataset.conflict]=select.value;
    notice(t('Syncing…','\u6b63\u5728\u540c\u6b65…'));
    const result=await request('apply',{previewId:preview.previewId,resolutions});connection=result.status;invalidate();
    // Rebuild section mappings and refresh the current compiled-preview status after a pull.
    latexOpenedFile=null;await loadProject(workspaceId);$('tab-assistant').click();
    notice(result.changed?t('Synced. Sections are updated; recompile to refresh the PDF.','\u540c\u6b65\u5b8c\u6210，\u7ae0\u8282\u5df2\u66f4\u65b0。\u91cd\u65b0\u7f16\u8bd1\u5373\u53ef\u66f4\u65b0 PDF。'):t('Sync complete.','\u540c\u6b65\u5b8c\u6210。'));
  });
})();
