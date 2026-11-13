'use strict';
(() => {
  const scopeNames={global:'个人全局',section_type:'个人章节类型',project:'当前论文',section:'当前章节'};
  const kindNames={preference:'写作偏好',library_preference:'参考写法偏好',author_style:'作者风格补充'};
  const statusNames={active:'已生效',pending:'待确认',disabled:'已停用',rejected:'已拒绝',accepted:'已合并'};
  const types=['abstract','introduction','related_work','preliminary','motivation','method','experiments','results','ablation','discussion','limitations','conclusion','appendix','references'];
  const openButton=document.createElement('button');openButton.id='preferences-open';openButton.type='button';openButton.textContent='写作偏好';
  $('conversation-toolbar').append(openButton);
  const notice=document.createElement('span');notice.id='preference-notice';notice.setAttribute('role','status');openButton.after(notice);
  const page=document.createElement('dialog');page.id='preferences-page';page.setAttribute('aria-label','写作偏好');
  page.innerHTML=`<header><div><small>Caret / Memory</small><h1>写作偏好</h1></div><button id="pref-close" type="button">返回写作</button></header>
    <div class="pref-controls"><label>查看章节 <select id="pref-section"></select></label><button id="pref-refresh">刷新</button><button id="pref-add">新增偏好</button><button id="pref-mark">标记满意版本</button><label><input id="pref-learning" type="checkbox">从聊天学习</label></div>
    <p class="pref-description">有偏好信号时，使用当前写作模型在后台分析相关对话，可能产生额外 API 用量。明确的长期新增要求自动记录，推断、规则替换及作者总结先待确认。更新从下一轮生效；恢复偏好不会回退论文。</p>
    <nav id="pref-tabs"></nav><p id="pref-status" role="status"></p><div id="pref-content"></div>`;
  document.body.append(page);
  const editor=document.createElement('dialog');editor.id='preference-editor';
  editor.innerHTML=`<form id="pref-edit-form"><h2>编辑写作偏好</h2><label>类型<select id="pref-kind"></select></label><label>适用范围<select id="pref-scope"></select></label><label>章节类型<select id="pref-type"></select></label><label>作者<select id="pref-author"><option value="">不指定</option><option value="xuefeng">Xuefeng Du</option><option value="hongxin">Hongxin Wei</option></select></label><label>具体规则<textarea id="pref-rule" rows="5" maxlength="800" required></textarea></label><label>修改原因<input id="pref-reason" maxlength="500" required></label><details><summary>作者总结的原文证据</summary><p>作者风格补充必须提供原文证据。聊天生成的建议会自动附带；普通个人偏好无需填写。</p><textarea id="pref-evidence" rows="5" aria-label="原文证据 JSON"></textarea></details><p id="pref-edit-status" role="status"></p><footer><button type="button" id="pref-edit-cancel">取消</button><button type="submit">保存并生效</button></footer></form>`;
  document.body.append(editor);
  const tabs={effective:'本章节生效',pending:'待确认',all:'全部个人偏好',library:'论文库参考',history:'版本历史',used:'本轮使用'};
  let data=null,tab='effective',workspaceId=null,sectionId=null,editing=null,snapshot=null,requestToken=0,working=false,editorBaseline='',editingVersion=null;
  const el=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;};
  const button=(label,fn)=>{const n=el('button',label);n.type='button';n.onclick=fn;return n;};
  function context(){return {...workspaceId?{workspaceId}:{},...sectionId?{sectionId}:{}};}
  function status(message){$('pref-status').textContent=message;}
  async function api(extra={},body=null){
    const query=new URLSearchParams({...context(),...extra});
    return localAPI('/api/preferences'+(body?'':'?'+query),{headers:{'Content-Type':'application/json','X-Draft-Preferences':'1'},...body?{method:'POST',body:JSON.stringify({...context(),expected:data.version,...body})}:{}});
  }
  function relevant(item){return !item.workspaceId||item.workspaceId===workspaceId;}
  async function load(){
    const token=++requestToken;status('正在读取偏好…');
    try{const result=await api();if(token!==requestToken||!page.open)return;data=result;
      $('pref-section').replaceChildren(new Option('全文讨论', ''),...data.sections.map(s=>new Option(s.title,s.id)));$('pref-section').value=sectionId||'';
      $('pref-learning').checked=data.learning;render();status('当前版本 '+data.version.slice(0,8)+' · 更新从下一轮生效');
    }catch(e){if(token===requestToken)status(e.message);}
  }
  async function change(payload){
    if(working)return;working=true;page.setAttribute('aria-busy','true');
    try{await api({},payload);await load();return true;}catch(e){status(e.message);return false;}
    finally{working=false;page.removeAttribute('aria-busy');}
  }
  function describe(i){return [kindNames[i.kind],scopeNames[i.scope],i.sectionType,(data?.sections.find(s=>s.id===i.sectionId)?.title||i.sectionId),i.author,statusNames[i.status]].filter(Boolean).join(' · ');}
  function card(i,readonly=false){
    const article=el('article',undefined,'pref-card');article.append(el('small',describe(i)),el('p',i.rule,'pref-rule'));
    if(i.source?.quote){const quote=el('blockquote',i.source.quote);article.append(quote);}
    if(i.reason)article.append(el('p','更新依据：'+i.reason));
    if(i.source?.runId)article.append(el('small','来源会话轮次：'+i.source.runId));
    if(i.targetId)article.append(el('small','拟修订已有规则，接受后替换该规则。'));
    for(const e of i.evidence||[])article.append(el('blockquote',e.paper+' · 第 '+e.page+' 页\n'+e.quote));
    if(!readonly){const actions=el('footer');
      if(i.status==='pending'){
        actions.append(button('修改建议',()=>edit(i)),button('接受',()=>change({action:'accept',id:i.id,reason:'用户确认聊天建议'})),button('拒绝',()=>change({action:'reject',id:i.id,reason:'用户拒绝聊天建议'})));
      }else if(['active','disabled'].includes(i.status)){
        actions.append(button('编辑与调整范围',()=>edit(i)),button(i.status==='active'?'停用':'重新启用',()=>change({action:i.status==='active'?'disable':'enable',id:i.id,reason:'用户调整生效状态'})));
      }
      article.append(actions);
    }return article;
  }
  function render(){
    $('pref-tabs').replaceChildren(...Object.entries(tabs).filter(([key])=>key!=='used'||snapshot).map(([key,label])=>{const b=button(label+(key==='pending'?' ('+data.items.filter(i=>i.status==='pending'&&relevant(i)).length+')':''),()=>{tab=key;render();});b.setAttribute('aria-current',String(tab===key));return b;}));
    const content=$('pref-content');content.replaceChildren();
    if(tab==='history'){
      content.append(el('p','每次修改都记录在独立的本地 Git 仓库。选择版本可比较差异或恢复，恢复也会留下新记录。'));
      for(const h of data.history){const a=el('article',undefined,'pref-card');a.append(el('strong',h.reason||h.action),el('p',new Date(h.at).toLocaleString()+' · '+h.actor+' · '+h.version.slice(0,8)),button('比较与恢复',()=>showVersion(h.version)));content.append(a);}
      if(data.historyMore)content.append(button('加载更早版本',async()=>{try{const next=await api({historyOffset:data.historyOffset+50});data.history.push(...next.history);data.historyOffset=next.historyOffset;data.historyMore=next.historyMore;render();}catch(e){status(e.message);}}));return;
    }
    if(tab==='library'){
      content.append(el('p','以下旧版作者记忆作为原文参考保留；新的风格补充在本页审核并纳入 Git，随对应章节偏好一起提供给写作模型。'));
      for(const m of data.authorMemories){const d=el('details');d.append(el('summary',m.author+' / '+m.section),el('pre',m.text||'尚无对应章节的作者记忆'));content.append(d);}
      const rows=data.items.filter(i=>relevant(i)&&['library_preference','author_style'].includes(i.kind));rows.forEach(i=>content.append(card(i)));if(!rows.length)content.append(el('p','尚无参考写法偏好或已审核的作者风格补充。'));return;
    }
    const rows=tab==='used'?(snapshot?.items||[]):tab==='effective'?data.effective:data.items.filter(i=>relevant(i)&&(tab==='pending'?i.status==='pending':i.status!=='pending'));
    if(tab==='used')content.append(el('p','这次写作实际读取的版本：'+(snapshot?.version||'未记录')+'。后续修改不会改变这份记录。'));
    if(!rows.length)content.append(el('p',tab==='pending'?'没有待确认建议。':'当前范围尚无偏好。可以新增，或在聊天中明确说明你的长期习惯。'));
    rows.forEach(i=>content.append(card(i,tab==='used')));
    if(tab==='used'&&snapshot?.legacyProjectPreferences){const d=el('details');d.append(el('summary','本轮读取的旧版论文偏好'),el('pre',snapshot.legacyProjectPreferences));content.append(d);}
    if(tab==='effective')for(const legacy of data.legacy){const d=el('details');d.append(el('summary',legacy.title),el('pre',legacy.text));content.append(d);}
  }
  function edit(item=null){
    if(working)return;editing=item;editingVersion=data.version;
    $('pref-kind').replaceChildren(...Object.entries(kindNames).map(([k,v])=>new Option(v,k)));
    $('pref-scope').replaceChildren(...Object.entries(scopeNames).map(([k,v])=>new Option(v,k)));
    $('pref-type').replaceChildren(new Option('选择章节类型',''),...types.map(t=>new Option(t,t)));
    $('pref-kind').value=item?.kind||'preference';$('pref-scope').value=item?.scope||(sectionId?'section':'global');$('pref-type').value=item?.sectionType||data.context.section_type||'';$('pref-author').value=item?.author||'';
    $('pref-rule').value=item?.rule||'';$('pref-reason').value='';$('pref-evidence').value=JSON.stringify(item?.evidence||[],null,2);$('pref-edit-status').textContent='';$('pref-edit-form').querySelector('button[type=submit]').textContent=item?.status==='pending'?'保存建议':'保存并生效';editorBaseline=editState();editor.showModal();
  }
  function editState(){return ['pref-kind','pref-scope','pref-type','pref-author','pref-rule','pref-reason','pref-evidence'].map(id=>$(id).value).join('\n');}
  function closeEditor(){if(editState()!==editorBaseline&&!confirm('放弃尚未保存的偏好修改？'))return;editor.close();}
  $('pref-edit-cancel').onclick=closeEditor;editor.addEventListener('cancel',e=>{e.preventDefault();closeEditor();});
  $('pref-edit-form').onsubmit=async e=>{e.preventDefault();if(working)return;
    try{const item={kind:$('pref-kind').value,scope:$('pref-scope').value,sectionType:$('pref-type').value,author:$('pref-author').value,rule:$('pref-rule').value,evidence:JSON.parse($('pref-evidence').value||'[]')};
      const ok=await change({action:'save',expected:editingVersion,id:editing?.id,item,reason:$('pref-reason').value});if(ok)editor.close();else $('pref-edit-status').textContent=$('pref-status').textContent;
    }catch(err){$('pref-edit-status').textContent=err.message;}
  };
  async function showVersion(version){
    try{const result=await api({version});if(!page.open)return;data=result;const content=$('pref-content');content.replaceChildren();
      content.append(button('返回版本列表',()=>{tab='history';render();}),el('h2','版本 '+version.slice(0,8)),el('p','以下差异从所选历史版本到当前版本。恢复会生成新提交，不会修改论文正文。'),el('p','比较规则内容与适用范围：'));
      const oldItems=new Map(result.detail.state.items.map(i=>[i.id,i])),currentItems=new Map(result.items.map(i=>[i.id,i]));
      let changed=0;
      for(const id of new Set([...oldItems.keys(),...currentItems.keys()])){
        const before=oldItems.get(id),after=currentItems.get(id);if(JSON.stringify(before)===JSON.stringify(after))continue;changed++;
        const row=el('article',undefined,'pref-card pref-diff');
        for(const [label,item] of [['历史版本',before],['当前版本',after]]){const column=el('div');column.append(el('strong',label),el('small',item?describe(item):'此版本不存在'),el('p',item?.rule||'', 'pref-rule'));row.append(column);}content.append(row);
      }
      if(!changed)content.append(el('p','与当前偏好内容相同。'));
      const raw=el('details');raw.append(el('summary','Git 原始差异'),el('pre',result.detail.diff||'与当前偏好内容相同。'));content.append(raw);
      const chooser=el('select');chooser.setAttribute('aria-label','恢复范围');chooser.append(new Option('恢复整套偏好',''));
      const items=new Map([...result.items,...result.detail.state.items].map(i=>[i.id,i]));for(const i of items.values())chooser.append(new Option((scopeNames[i.scope]||'')+' · '+i.rule.slice(0,65),i.id));
      content.append(chooser,button('恢复所选版本',async()=>{if(!confirm(chooser.value?'将这条偏好恢复到所选版本？':'将整套偏好恢复到所选版本？其他论文的偏好也会受影响，论文正文不会改变。'))return;tab='history';await change({action:'restore',expected:result.version,id:chooser.value||undefined,revision:version,reason:'恢复偏好至 '+version.slice(0,8)});}));
    }catch(e){status(e.message);}
  }
  async function open(used=null){workspaceId=project?.id||null;sectionId=selected()?.id||null;snapshot=used;tab=used?'used':'effective';if(!page.open)page.showModal();await load();}
  openButton.onclick=()=>open();$('pref-close').onclick=()=>page.close();$('pref-refresh').onclick=load;$('pref-add').onclick=()=>data&&edit();
  $('pref-section').onchange=()=>{sectionId=$('pref-section').value||null;load();};
  $('pref-learning').onchange=async()=>{const enabled=$('pref-learning').checked;if(!await change({action:'learning',enabled,reason:enabled?'开启聊天偏好学习':'暂停聊天偏好学习'}))$('pref-learning').checked=data.learning;};
  $('pref-mark').onclick=async()=>{if(!data)return;const reason=window.prompt('为当前满意版本命名，例如：Introduction 满意版');if(reason?.trim())await change({action:'mark',reason:reason.trim()});};
  const renderBefore=renderEntry;renderEntry=function(entry){const node=renderBefore(entry);const used=entry.agent?.context?.preferences;if(used)node.append(button('本轮偏好 · '+used.items.length+' 条',()=>open(used)));return node;};
  const jobs=new Map();
  window.DraftPreferences={open,afterTurn(result){
    const learning=result.preferenceLearning;if(!learning||learning.status==='skipped')return;
    if(learning.status==='failed'){notice.textContent=learning.message;return;}
    const wid=project?.id,runId=result.runId;
    if(jobs.has(runId))return;
    notice.textContent='正在整理写作偏好…';
    let attempts=0;
    const poll=async()=>{try{
      const value=await localAPI('/api/preferences/job?'+new URLSearchParams({runId,workspaceId:wid}),{headers:{'X-Draft-Preferences':'1'}});
      if(value.status==='running'&&attempts++<36){jobs.set(runId,setTimeout(poll,5000));return;}
      jobs.delete(runId);
      notice.textContent=value.status==='done'?(value.active||value.pending?'偏好更新：'+value.active+' 条生效，'+value.pending+' 条待确认':'本轮没有新增长期偏好'):value.message||'偏好分析仍在后台进行，可稍后刷新偏好页面。';
      if(page.open)await load();
    }catch{jobs.delete(runId);notice.textContent='偏好状态暂时无法读取，可打开页面刷新。';}};
    jobs.set(runId,setTimeout(poll,1000));
  }};
})();
