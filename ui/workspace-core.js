/* Pure workspace rules; shared by the browser and regression tests. */
(function(root){
const copy=x=>JSON.parse(JSON.stringify(x));
const uid=()=>globalThis.crypto?.randomUUID?.()||Date.now().toString(36)+'-'+Math.random().toString(36).slice(2);
function makeSection(s,i){return {id:uid(),title:s.title,start_page:s.start_page,end_page:s.end_page,filename:String(i+1).padStart(2,'0')+'-'+(s.title.toLowerCase().replace(/[^a-z0-9\u4e00-\u9fff]+/g,'-').replace(/^-|-$/g,'').slice(0,70)||'section')+'.md',text:'',initialized:false,versions:[],chat:[],input:'',pending:null};}
function commit(s,text,reason){if(typeof text!=='string')throw new Error('正文必须是文字');if(s.initialized&&s.text===text)return false;s.text=text;s.initialized=true;s.versions.push({id:uid(),at:new Date().toISOString(),reason,text});return true;}
function context(sections,target){return JSON.stringify({instruction:'仅当前章节最新稿；其他章节与 PDF 由 agent 按需读取。',target:target?{file:target.filename,title:target.title,version:target.versions.length,text:target.text}:null});}
function proposal(s,text,source){return {id:uid(),base:s.versions.at(-1)?.id||null,text,source,at:new Date().toISOString()};}
function latexRevision(s,entry){
  if(!entry.baseVersion||entry.baseVersion!==s.versions.at(-1)?.id)throw new Error('这条回复不是基于当前版本，请让 Gemini 根据当前稿重新给出完整 LaTeX 修改稿。');
  const matches=[...entry.text.matchAll(/^```(?:latex|tex)[ \t]*\r?\n([\s\S]*?)^```[ \t]*$/gmi)];
  if(matches.length!==1||!matches[0][1].trim())throw new Error('需要一个完整的 LaTeX 代码块才能直接采用。请让 Gemini 将当前章节的完整修改稿放在一个 latex 代码块中，或使用“编辑当前稿”手动修改。');
  // The fence is only a transport wrapper. Preserve the source, including its trailing newline.
  return {...proposal(s,matches[0][1],entry.id),notes:'Gemini 原始 LaTeX 修改稿 · 未经 GPT 整理。请核对这是否是当前章节的完整稿；确认后写回 '+(s.source_file||s.filename)+'。'};
}
function accept(s){if(!s.pending)throw new Error('没有待采用稿');if(s.pending.base!==(s.versions.at(-1)?.id||null))throw new Error('当前稿已变化，请重新生成修改稿。');commit(s,s.pending.text,s.format==='latex'?'采用 Gemini LaTeX 修改':'采用 Gemini 修改 · OpenAI 整理');s.pending=null;}
root.WorkspaceCore={copy,uid,makeSection,commit,context,proposal,accept,latexRevision};
if(typeof module!=='undefined')module.exports=root.WorkspaceCore;
})(globalThis);
