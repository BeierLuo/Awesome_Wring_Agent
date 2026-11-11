'use strict';
// Rendering is a view only: never write generated HTML back to a draft or chat.
window.DraftMarkdown=(()=>{
  const views=new WeakMap();
  const escape=text=>String(text).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  function render(target,source){
    source=String(source??'');target.classList.add('markdown-content');
    if(!window.marked||!window.DOMPurify||!window.katex||source.length>300000){target.textContent=source;return;}
    const equations=[];
    function mathHTML(token){
      const id=equations.push(token)-1;
      return token.display?'<div class="math-block" data-draft-math="'+id+'"></div>':'<span data-draft-math="'+id+'"></span>';
    }
    const parser=new marked.Marked({gfm:true,breaks:false,renderer:{
      html({text}){return escape(text);},
      // Do not automatically fetch URLs embedded by a model or an imported document.
      image({text}){return '<span class="image-description">[图片：'+escape(text||'未命名')+']</span>';}
    },extensions:[{
      name:'displayMath',level:'block',start(src){return src.search(/^(?: {0,3})(?:\$\$|\\\[)/m);},
      tokenizer(src){
        const match=/^ {0,3}\$\$([\s\S]+?)\$\$[ \t]*(?:\n|$)/.exec(src)||/^ {0,3}\\\[([\s\S]+?)\\\][ \t]*(?:\n|$)/.exec(src);
        if(match)return {type:'displayMath',raw:match[0],text:match[1],display:true};
      },renderer:mathHTML
    },{
      name:'inlineMath',level:'inline',start(src){return src.search(/\$|\\[([]/);},
      tokenizer(src){
        const open=src.startsWith('$$')?'$$':src.startsWith('\\(')?'\\(':src.startsWith('\\[')?'\\[':src.startsWith('$')?'$':null;
        if(!open)return;
        const close=open==='\\('? '\\)':open==='\\['?'\\]':open;
        let end=open.length;
        while((end=src.indexOf(close,end))>=0){
          let backslashes=0;for(let i=end-1;i>=0&&src[i]==='\\';i--)backslashes++;
          if(backslashes%2){end+=close.length;continue;}
          const text=src.slice(open.length,end);
          if(!text||open==='$'&&(/^\s|\s$|\n/.test(text)||/\d/.test(src[end+1]||'')))return;
          return {type:'inlineMath',raw:src.slice(0,end+close.length),text,display:open==='$$'||open==='\\['};
        }
      },renderer:mathHTML
    }]});
    try{
      target.innerHTML=DOMPurify.sanitize(parser.parse(source),{USE_PROFILES:{html:true},FORBID_TAGS:['style','img','input','form','button'],FORBID_ATTR:['style','id','name'],ALLOW_DATA_ATTR:true});
      for(const node of target.querySelectorAll('[data-draft-math]')){
        const formula=equations[Number(node.dataset.draftMath)];node.removeAttribute('data-draft-math');
        if(!formula)continue;
        if(formula.text.length>20000){node.textContent=formula.raw;continue;}
        try{katex.render(formula.text,node,{displayMode:formula.display,throwOnError:false,trust:false,strict:'ignore',maxExpand:1000,maxSize:20,macros:{}});}
        catch{node.textContent=formula.raw;}
      }
      for(const link of target.querySelectorAll('a')){
        const href=link.getAttribute('href')||'';
        if(!/^(https?:\/\/|mailto:|#)/i.test(href))link.removeAttribute('href');
        link.setAttribute('target','_blank');link.setAttribute('rel','noopener noreferrer');
      }
      for(const table of target.querySelectorAll('table')){
        const wrapper=document.createElement('div');wrapper.className='markdown-table';table.replaceWith(wrapper);wrapper.append(table);
      }
    }catch{target.textContent=source;}
  }
  function mount(target,source){
    source=String(source??'');let view=views.get(target);
    if(!view){
      target.replaceChildren();target.classList.add('markdown-view');
      const toolbar=document.createElement('div');toolbar.className='markdown-toolbar';
      const toggle=document.createElement('button');toggle.type='button';toggle.textContent='查看源码';toggle.setAttribute('aria-pressed','false');
      const preview=document.createElement('div'),raw=document.createElement('pre');raw.className='markdown-source';raw.hidden=true;
      toolbar.append(toggle);target.append(toolbar,preview,raw);view={toggle,preview,raw,source:null};views.set(target,view);
      toggle.onclick=()=>{const showingSource=raw.hidden;raw.hidden=!showingSource;preview.hidden=showingSource;toggle.textContent=showingSource?'查看排版':'查看源码';toggle.setAttribute('aria-pressed',String(showingSource));};
    }
    if(view.source!==source){view.source=source;view.raw.textContent=source;render(view.preview,source);}
  }
  return {render,mount};
})();
