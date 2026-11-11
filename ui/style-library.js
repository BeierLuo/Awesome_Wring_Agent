'use strict';
let libraryItems=[],libraryRunning=false,libraryStop=false,libraryProject=null;
const libraryAPI=(path='',body)=>localAPI('/api/style-library'+path,{method:body?'POST':'GET',headers:{'Content-Type':'application/json','X-Draft-Library':'1'},...(body?{body:JSON.stringify(body)}:{})});
const libraryIds=()=>Array.from($('library-papers').selectedOptions).map(o=>o.value);
function libraryStatus(text){$('library-status').textContent=text;}
function libraryWorking(value){libraryRunning=value;for(const id of ['library-upload','library-overview','library-papers','library-analyze','library-search','library-apply','library-clear','library-close','library-role','library-query'])$(id).disabled=value;$('library-stop').hidden=!value;}
async function libraryRefresh(ids=libraryIds()){
 const data=await libraryAPI();libraryItems=data.items;
 $('library-papers').replaceChildren(...data.items.map(p=>{const o=new Option(p.name+' · '+p.done+'/'+p.batches+' 已分析',p.id);o.selected=ids.includes(p.id);return o;}));
 $('library-count').textContent=data.items.length+' 篇 · '+data.root;
 if(!$('library-role').options.length){$('library-role').append(new Option('不限段落作用',''));for(const [id,label] of Object.entries(data.roles))$('library-role').append(new Option(label,id));}
}
$('library-open').onclick=async()=>{
 if(busy||loadingFile)return;libraryProject=project?.id||null;$('library-dialog').showModal();libraryStatus('正在读取本地论文库…');
 try{await libraryRefresh([]);const config=libraryProject?await libraryAPI('/selection?'+new URLSearchParams({workspaceId:libraryProject})):{paper_ids:[],role:'',query:''};await libraryRefresh(config.paper_ids);$('library-role').value=config.role;$('library-query').value=config.query;$('library-results').replaceChildren();libraryStatus('选中最多3篇作为参考；不选论文时可在全库寻找范例。新论文先分析，之后重复使用缓存。');}catch(e){libraryStatus(e.message);}
};
$('library-close').onclick=()=>$('library-dialog').close();
$('library-dialog').addEventListener('cancel',e=>{if(libraryRunning){e.preventDefault();libraryStop=true;libraryStatus('当前分析批次完成后停止，已完成结果会保留。');}});
$('library-stop').onclick=()=>{libraryStop=true;libraryStatus('当前批次完成后停止。');};
$('library-upload').onchange=async e=>{
 const files=Array.from(e.target.files||[]);if(!files.length)return;libraryWorking(true);
 try{for(const file of files){if(file.size>25*1024*1024)throw new Error(file.name+' 超过25 MB');libraryStatus('正在本地索引 '+file.name);const data=await new Promise((resolve,reject)=>{const r=new FileReader();r.onload=()=>resolve(r.result.split(',')[1]);r.onerror=()=>reject(new Error('无法读取 PDF'));r.readAsDataURL(file);});await libraryAPI('/upload',{name:file.name,data});}await libraryRefresh();libraryStatus('上传完成。选中论文后点击“分析写作风格”；原文保存在本地，分析会调用 GPT。');}catch(err){libraryStatus(err.message);}finally{e.target.value='';libraryWorking(false);}
};
$('library-analyze').onclick=async()=>{
 const ids=libraryIds();if(!ids.length){libraryStatus('请先选中要分析的论文（可以多选）。');return;}libraryWorking(true);libraryStop=false;
 try{for(const id of ids){let p=libraryItems.find(p=>p.id===id);while(p.done<p.batches&&!libraryStop){libraryStatus('GPT 分析 '+p.name+' · '+(p.done+1)+'/'+p.batches+'，已完成的分析会缓存');p=await libraryAPI('/analyze',{paper_id:id});await libraryRefresh(ids);}if(libraryStop)break;}libraryStatus(libraryStop?'已停止，可继续未完成的批次。':'所选论文分析完成，可以寻找范例或设为写作参考。');}catch(e){libraryStatus(e.message+' 已完成的批次保留，再点击分析可继续。');}finally{libraryWorking(false);}
};
$('library-search').onclick=async()=>{
 libraryWorking(true);const ids=libraryIds();libraryStatus('正在查找范例…');
 try{await libraryRefresh(ids);const result=await libraryAPI('/search',{paper_ids:ids.length?ids:null,role:$('library-role').value,query:$('library-query').value});$('library-results').replaceChildren();
 for(const e of result.examples){const card=document.createElement('article');card.className='library-example';const title=document.createElement('strong');title.textContent=e.paper+' · 第 '+e.page+' 页 · '+e.section;const source=document.createElement('blockquote');source.textContent=e.text;const analysis=document.createElement('p');analysis.textContent='段落作用：'+e.purpose+'\n逻辑推进：'+e.logic+'\n句子作用：'+e.sentence_moves.join(' → ')+'\n表达方式：'+e.wording;const button=document.createElement('button');button.textContent='查看原 PDF';button.onclick=async()=>{try{const response=await fetch('/api/style-library/pdf?id='+e.paper_id,{headers:{'X-Draft-Library':'1'}});if(!response.ok)throw new Error('无法读取原 PDF');const url=URL.createObjectURL(await response.blob());const a=document.createElement('a');a.href=url+'#page='+e.page;a.target='_blank';a.rel='noopener';a.click();setTimeout(()=>URL.revokeObjectURL(url),60000);}catch(error){libraryStatus(error.message);}};const use=document.createElement('button');use.textContent='以这篇为写作参考';use.onclick=()=>{for(const option of $('library-papers').options)option.selected=option.value===e.paper_id;$('library-role').value=e.role;libraryStatus('已选定 '+e.paper+'。点击“用于当前章节改写”保存参考并准备请求。');};card.append(title,source,analysis,button,use);$('library-results').append(card);}
 libraryStatus((result.examples.length?'找到 '+result.examples.length+' 个范例。':'暂无匹配范例。')+(result.pending.length?' 有 '+result.pending.length+' 篇尚未分析完成，可选中后继续分析。':'')+' 原文按 PDF 文本块提取，可能包含断行；页码可用于核对。');
 }catch(e){libraryStatus(e.message);}finally{libraryWorking(false);}
};
$('library-apply').onclick=async()=>{
 if(!libraryProject||libraryProject!==project?.id||!selected()){libraryStatus('请先选择 Project 中要修改的章节，再打开论文库。');return;}
 const ids=libraryIds();if(!ids.length||ids.length>3){libraryStatus('请指定1–3篇参考论文。');return;}if(ids.some(id=>!libraryItems.find(p=>p.id===id).done)){libraryStatus('所选论文尚无风格分析，请先点击“分析写作风格”。');return;}
 libraryWorking(true);try{await libraryAPI('/selection',{workspaceId:libraryProject,paper_ids:ids,role:$('library-role').value,query:$('library-query').value});const names=ids.map(id=>libraryItems.find(p=>p.id===id).name).join('、');const instruction='请参照 '+names+' 的写作风格修改当前章节'+($('library-role').value?'，重点借鉴“'+$('library-role').selectedOptions[0].textContent+'”的段落组织':'')+'。'+$('library-query').value+' 保持本论文事实、数据和引用不变，说明借鉴来源与方式。';$('prompt').value=[$('prompt').value.trim(),instruction].filter(Boolean).join('\n');active().input=$('prompt').value;await persist();$('library-dialog').close();localStatus('写作参考已保存到当前 Project。检查输入后点击发送；之后的对话也会使用这些参考，可在论文库中清除。');}catch(e){libraryStatus(e.message);}finally{libraryWorking(false);}
};
$('library-clear').onclick=async()=>{if(!libraryProject)return;try{await libraryAPI('/selection',{workspaceId:libraryProject,paper_ids:[],role:'',query:''});await libraryRefresh([]);libraryStatus('当前 Project 的写作参考已清除，论文库文件保留。');}catch(e){libraryStatus(e.message);}};

$('library-overview').onclick=async()=>{
 const ids=libraryIds();if(!ids.length){libraryStatus('请先选中论文。');return;}libraryWorking(true);
 try{$('library-results').replaceChildren();for(const id of ids){const result=await libraryAPI('/analysis?'+new URLSearchParams({id}));const card=document.createElement('article');card.className='library-example';const title=document.createElement('strong');title.textContent=result.paper.name+' · 已分析 '+result.paper.done+'/'+result.paper.batches+' 批';const text=document.createElement('p');text.textContent=result.overviews.map((s,i)=>'第 '+(i+1)+' 批分析\n'+s).join('\n\n')||'尚未分析';card.append(title,text);$('library-results').append(card);}libraryStatus('按原文顺序展示分批概要；未完成的批次不包含在内。逐段和逐句分析可通过“寻找段落范例”查看。');}catch(e){libraryStatus(e.message);}finally{libraryWorking(false);}
};
