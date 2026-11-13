'use strict';
let strategyProject=null,strategyProposal=null,strategyMemory=null,strategyBusy=false;
function strategyStatus(text){$('strategy-status').textContent=text;}
function strategyWorking(value){strategyBusy=value;for(const id of ['strategy-close','strategy-library','strategy-recommend','strategy-mode','strategy-section','strategy-goal','strategy-enable','strategy-memory-read','strategy-memory-save','strategy-memory-build','strategy-author'])$(id).disabled=value;document.querySelectorAll('.strategy-adopt').forEach(b=>b.disabled=value);}
const originalLibraryOpen=$('library-open').onclick;
$('library-open').textContent='写作策略 · 论文库';
$('library-open').onclick=async()=>{
 if(busy||loadingFile)return;if(!project){localStatus('请先新建或打开一个 Project。');return;}
 strategyProject=project.id;strategyProposal=null;strategyMemory=null;$('strategy-memory-editor').hidden=true;$('strategy-options').replaceChildren();$('strategy-dialog').showModal();strategyWorking(true);
 try{const result=await libraryAPI('/strategy?'+new URLSearchParams({workspaceId:strategyProject,sectionId:selected()?.id||''}));$('strategy-mode').value=result.settings.mode;$('strategy-goal').value=result.dashboard?.selected_plan?.goal||result.settings.goal;$('strategy-section').replaceChildren(...Object.entries(result.sections).map(([k,v])=>new Option(v,k)));$('strategy-section').prepend(new Option('请选择当前章节类型',''));$('strategy-section').value=result.dashboard?.current_section||'';strategyStatus('无需先指定论文。GPT 会结合当前章节、hook 和贡献比较不同写法；推荐是待选方案，不自动改稿。');}catch(e){strategyStatus(e.message);}finally{strategyWorking(false);}
};
function strategyDirty(){return strategyMemory&&$('strategy-memory-text').value!==strategyMemory.text;}
function closeStrategy(){if(strategyBusy)return;if(strategyDirty()&&!confirm('放弃未保存的章节记忆修改？'))return;$('strategy-dialog').close();strategyMemory=null;}
$('strategy-close').onclick=closeStrategy;
$('strategy-dialog').addEventListener('cancel',e=>{e.preventDefault();closeStrategy();});
$('strategy-library').onclick=async()=>{if(strategyDirty()&&!confirm('放弃未保存的记忆修改？'))return;$('strategy-dialog').close();await originalLibraryOpen();};
$('strategy-enable').onclick=async()=>{
 strategyWorking(true);try{await libraryAPI('/strategy-settings',{workspaceId:strategyProject,mode:$('strategy-mode').value,goal:$('strategy-goal').value});strategyStatus('偏好已保存。Agent 每轮只收到当前章节的记忆导航，按需查规则和原文；不会载入整库。');}catch(e){strategyStatus(e.message);}finally{strategyWorking(false);}
};
$('strategy-recommend').onclick=async()=>{
 const target=selected();if(!target||strategyProject!==project?.id){strategyStatus('请先选择要写的章节。');return;}
 if($('strategy-mode').value==='off'){strategyStatus('请先选择自动推荐或作者风格。');return;}
 strategyWorking(true);strategyStatus('GPT 正在比较当前 hook、贡献形态和章节任务，准备2–3种写法…');
 try{if(!await persist())throw new Error('请先解决 Project 保存问题');const r=await libraryAPI('/recommend',{workspaceId:strategyProject,sectionId:target.id,section:$('strategy-section').value,mode:$('strategy-mode').value,goal:$('strategy-goal').value});strategyProposal=r;$('strategy-options').replaceChildren();const diagnosis=document.createElement('p');diagnosis.textContent=r.diagnosis+(r.missing_information.length?'\n待补信息：'+r.missing_information.join('；'):'');$('strategy-options').append(diagnosis);
 r.options.forEach((o,index)=>{const card=document.createElement('article');card.className='strategy-card';const heading=document.createElement('h3');heading.textContent=o.title;const body=document.createElement('p');body.textContent='借鉴样本：'+({hongxin:'Hongxin Wei',xuefeng:'Xuefeng Du',mixed:'组合路线'}[o.author])+'\nHook：'+o.hook+'\n贡献定位：'+o.contribution_framing+'\n段落计划：\n'+o.paragraph_plan.map((x,i)=>(i+1)+'. '+x).join('\n')+'\n为什么适合：'+o.why_fit+'\n不适用与风险：'+o.risks.join('；')+'\n参考依据：'+o.sources.map(s=>s.paper+' 第 '+s.page+' 页').join('；');const adopt=document.createElement('button');adopt.className='strategy-adopt';adopt.textContent='选用这条路线';adopt.onclick=()=>adoptStrategy(index);card.append(heading,body,adopt);$('strategy-options').append(card);});strategyStatus('请选择更符合论文事实的路线。选用后保存到该章节的小型计划文件，正文仍需确认采用。');
 }catch(e){strategyStatus(e.message);}finally{strategyWorking(false);}
};
async function adoptStrategy(index){strategyWorking(true);try{const result=await libraryAPI('/adopt-strategy',{workspaceId:strategyProject,proposal_id:strategyProposal.id,index});const request='请按照已选定的“'+result.option.title+'”章节写作计划修改当前稿。'+result.goal+' 保留当前论文事实；需要具体写法时按需读取章节风格记忆和参考原文。';$('prompt').value=[$('prompt').value.trim(),request].filter(Boolean).join('\n');active().input=$('prompt').value;if(!await persist())throw new Error('计划已保存，但请求保存失败，请重载 Project');$('strategy-dialog').close();localStatus('章节计划已保存。检查输入后发送；切换章节会读取对应的小型记忆。');}catch(e){strategyStatus(e.message);}finally{strategyWorking(false);}}
async function readStrategyMemory(){
 if(strategyDirty()&&!confirm('放弃未保存的记忆修改？'))return;strategyWorking(true);
 try{const m=await libraryAPI('/memory?'+new URLSearchParams({author:$('strategy-author').value,section:$('strategy-section').value}));strategyMemory=m;$('strategy-memory-editor').hidden=false;$('strategy-memory-path').textContent=m.path;$('strategy-memory-text').value=m.text;strategyStatus(m.exists?'可编辑这份独立章节记忆；保存后下次按需读取时生效。':'该章节尚无规则，可从已分析论文归纳。');}catch(e){strategyStatus(e.message);}finally{strategyWorking(false);}
}
$('strategy-memory-read').onclick=readStrategyMemory;
$('strategy-memory-save').onclick=async()=>{if(!strategyMemory)return;strategyWorking(true);try{strategyMemory=await libraryAPI('/save-memory',{author:strategyMemory.author,section:strategyMemory.section,text:$('strategy-memory-text').value,sha256:strategyMemory.sha256});strategyStatus('章节记忆已保存，旧版本保留。');}catch(e){strategyStatus(e.message);}finally{strategyWorking(false);}};
$('strategy-memory-build').onclick=async()=>{if(strategyDirty()&&!confirm('放弃未保存的修改并重新归纳该章节规则？'))return;strategyWorking(true);strategyStatus('GPT 正在从跨论文范例归纳本章节的条件性写作规则…');try{strategyMemory=await libraryAPI('/build-memory',{author:$('strategy-author').value,section:$('strategy-section').value});$('strategy-memory-editor').hidden=false;$('strategy-memory-path').textContent=strategyMemory.path;$('strategy-memory-text').value=strategyMemory.text;strategyStatus('章节规则已更新，来源与适用条件已保留；旧版在历史文件夹中。');}catch(e){strategyStatus(e.message);}finally{strategyWorking(false);}};
window.addEventListener('beforeunload',e=>{if(strategyDirty()){e.preventDefault();e.returnValue='';}});
