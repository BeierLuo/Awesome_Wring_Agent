/* Pure workspace rules; shared by the browser and regression tests. */
(function(root){
const copy=x=>JSON.parse(JSON.stringify(x));
const uid=()=>globalThis.crypto?.randomUUID?.()||Date.now().toString(36)+'-'+Math.random().toString(36).slice(2);
function makeSection(s,i){return {id:uid(),title:s.title,start_page:s.start_page,end_page:s.end_page,filename:String(i+1).padStart(2,'0')+'-'+(s.title.toLowerCase().replace(/[^a-z0-9\u4e00-\u9fff]+/g,'-').replace(/^-|-$/g,'').slice(0,70)||'section')+'.md',text:'',initialized:false,versions:[],chat:[],input:'',pending:null};}
function selectionRequest(s){
  const focus=s?.paragraphTarget;if(!focus)return null;
  if(focus.stale||focus.version!==s.versions.at(-1)?.id||s.text.slice(focus.start,focus.end)!==focus.text)throw new Error('选中段落已变化，请重新选择或取消选择后发送。');
  return {start:Array.from(s.text.slice(0,focus.start)).length,end:Array.from(s.text.slice(0,focus.end)).length,text:focus.text,version:focus.version};
}
function rebaseSelection(s,text){
  const f=s.paragraphTarget;if(!f)return;
  if(f.stale||f.version!==s.versions.at(-1)?.id||s.text.slice(f.start,f.end)!==f.text){f.stale=true;return;}
  const old=s.text;let a=0,b=old.length,c=text.length;
  while(a<b&&a<c&&old[a]===text[a])a++;
  while(b>a&&c>a&&old[b-1]===text[c-1]){b--;c--;}
  const delta=text.length-old.length;
  if(b<=f.start&&a<f.start){f.start+=delta;f.end+=delta;}
  else if(a>=f.start&&b<=f.end)f.end+=delta;
  else if(a<f.end){f.stale=true;return;}
  f.text=text.slice(f.start,f.end);if(!f.text.trim())f.stale=true;
}
function commit(s,text,reason){if(typeof text!=='string')throw new Error('正文必须是文字');if(s.initialized&&s.text===text)return false;rebaseSelection(s,text);s.text=text;s.initialized=true;s.versions.push({id:uid(),at:new Date().toISOString(),reason,text});if(s.paragraphTarget&&!s.paragraphTarget.stale)s.paragraphTarget.version=s.versions.at(-1).id;return true;}
function conversationStart(thread){const start=thread?.contextStart;return Number.isInteger(start)&&start>=0&&start<=(thread?.chat?.length||0)?start:0;}
function currentChat(thread){return (thread?.chat||[]).slice(conversationStart(thread));}
function ensureConversations(thread){
  if(!Array.isArray(thread.conversations))thread.conversations=[];
  if(!thread.conversationId){
    const start=conversationStart(thread);
    if(start>0)thread.conversations.push({id:uid(),chat:copy(thread.chat.slice(0,start)),input:'',created:thread.chat[0]?.at||''});
    thread.chat=currentChat(thread);thread.contextStart=0;
    thread.conversationId=uid();thread.conversationCreated=thread.chat[0]?.at||new Date().toISOString();
  }
}
function changeConversation(thread,id=null){
  ensureConversations(thread);
  if(id===thread.conversationId)return;
  const index=id===null?-1:thread.conversations.findIndex(c=>c.id===id);
  if(id!==null&&index<0)throw new Error('历史会话不存在');
  const next=index>=0?thread.conversations.splice(index,1)[0]:{id:uid(),chat:[],input:'',created:new Date().toISOString()};
  if(thread.chat.length||thread.input)thread.conversations.push({id:thread.conversationId,chat:thread.chat,input:thread.input||'',created:thread.conversationCreated});
  thread.conversationId=next.id;thread.conversationCreated=next.created;
  thread.chat=next.chat;thread.input=next.input||'';thread.contextStart=0;
}
function conversationHistory(thread){
  if(!thread)return [];
  if(!thread.conversationId){
    const start=conversationStart(thread);
    return [{id:'current',chat:currentChat(thread),current:true},...(start?[{id:'legacy',chat:thread.chat.slice(0,start)}]:[])];
  }
  return [{id:thread.conversationId,chat:thread.chat,current:true},...(thread.conversations||[]).slice().reverse()];
}
function context(sections,target){return JSON.stringify({instruction:'仅当前章节最新稿；其他章节与 PDF 由 agent 按需读取。',target:target?{file:target.filename,title:target.title,version:target.versions.length,text:target.text}:null});}
function proposal(s,text,source){return {id:uid(),base:s.versions.at(-1)?.id||null,text,source,at:new Date().toISOString()};}
function latexRevision(s,entry){
  if(!entry.baseVersion||entry.baseVersion!==s.versions.at(-1)?.id)throw new Error('这条回复不是基于当前版本，请让 写作 Agent 根据当前稿重新给出 LaTeX 修改。');
  let scopeStart=0,scopeEnd=s.text.length;
  if(entry.selection){
    const focus=entry.selection,chars=Array.from(s.text);
    if(!Number.isInteger(focus.start)||!Number.isInteger(focus.end)||focus.start<0||focus.end<=focus.start||focus.end>chars.length)throw new Error('段落修改范围无效');
    scopeStart=chars.slice(0,focus.start).join('').length;scopeEnd=chars.slice(0,focus.end).join('').length;
    if(focus.version!==entry.baseVersion||s.text.slice(scopeStart,scopeEnd)!==focus.text)throw new Error('选中段落已变化，请重新生成修改。');
  }
  const patches=[...entry.text.matchAll(/^```latex-edit[ \t]*\r?\n([\s\S]*?)^```[ \t]*$/gmi)];
  const matches=[...entry.text.matchAll(/^```(?:latex|tex)[ \t]*\r?\n([\s\S]*?)^```[ \t]*$/gmi)];
  if(/^```latex-edit\b/im.test(entry.text)){
    if(patches.length!==1||matches.length)throw new Error('局部修改需要唯一一个 latex-edit 代码块，不能混用整章修改稿。');
    let patch;
    try{patch=JSON.parse(patches[0][1]);}catch{throw new Error('局部修改格式无效，请重新生成。');}
    if(!patch||!Array.isArray(patch.edits)||!patch.edits.length)throw new Error('局部修改缺少 edits 列表。');
    // Resolve every edit against the same original. Never let one edit match another edit's output.
    const ranges=patch.edits.map(edit=>{
      if(!edit||typeof edit.old!=='string'||!edit.old.length||typeof edit.new!=='string')throw new Error('每处局部修改必须包含非空 old 原文和 new 修改稿。');
      const scope=s.text.slice(scopeStart,scopeEnd),local=scope.indexOf(edit.old),start=scopeStart+local;
      if(local<0||scope.indexOf(edit.old,local+1)!==-1)throw new Error('待替换原文不存在或位置不唯一，请根据当前稿重新生成局部修改。');
      return {start,end:start+edit.old.length,text:edit.new};
    }).sort((a,b)=>a.start-b.start);
    for(let i=1;i<ranges.length;i++)if(ranges[i].start<ranges[i-1].end)throw new Error('局部修改范围重叠，请合并后重新生成。');
    let text=s.text;
    for(const edit of ranges.slice().reverse())text=text.slice(0,edit.start)+edit.text+text.slice(edit.end);
    return {...proposal(s,text,entry.id),notes:'仅替换精确匹配的段落，其余源码保持不变；确认后写回 '+(s.source_file||s.filename)+'。'};
  }
  if(matches.length!==1||!matches[0][1].trim())throw new Error('需要一个完整的 LaTeX 修改代码块才能直接采用。请让 写作 Agent 用 latex-edit 返回段落修改，或使用“编辑当前稿”手动修改。');
  if(entry.selection&&(matches[0][1].slice(0,scopeStart)!==s.text.slice(0,scopeStart)||!matches[0][1].endsWith(s.text.slice(scopeEnd))||matches[0][1].length<scopeStart+s.text.length-scopeEnd))throw new Error('修改超出了选中段落，请使用 latex-edit 仅修改选区。');
  // The fence is only a transport wrapper. Preserve the source, including its trailing newline.
  return {...proposal(s,matches[0][1],entry.id),notes:'写作 Agent 原始 LaTeX 修改稿 · 未经 GPT 整理。请核对这是否是当前章节的完整稿；确认后写回 '+(s.source_file||s.filename)+'。'};
}
function accept(s){if(!s.pending)throw new Error('没有待采用稿');if(s.pending.base!==(s.versions.at(-1)?.id||null))throw new Error('当前稿已变化，请重新生成修改稿。');commit(s,s.pending.text,s.format==='latex'?'采用 写作 Agent LaTeX 修改':'采用 写作 Agent 修改 · OpenAI 整理');s.pending=null;}
root.WorkspaceCore={copy,uid,selectionRequest,ensureConversations,changeConversation,conversationHistory,conversationStart,currentChat,makeSection,commit,context,proposal,accept,latexRevision};
if(typeof module!=='undefined')module.exports=root.WorkspaceCore;
})(globalThis);
