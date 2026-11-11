'use strict';
let settingsDirty=false, settingsLoading=true, settingsLoaded=false;
const editedConfigFields=new Set();
const configFields={gemini_key:'key',gemini_model:'model',openai_key:'openai-key',openai_model:'openai-model',writer_provider:'writer-provider',...gcpFields};
const configDefaults={writer_provider:'gcp',gcp_auth:'express',gcp_location:'global',gcp_model:'gemini-4-argon',openai_model:'gpt-4.1'};
Object.values(configFields).forEach(id=>['input','change'].forEach(event=>$(id).addEventListener(event,()=>{settingsDirty=true;editedConfigFields.add(id);})));
async function settingsAPI(method,body){const r=await fetch('/api/settings',{method,headers:{'X-Draft-Settings':'1',...(body?{'Content-Type':'application/json'}:{})},...(body?{body:JSON.stringify(body)}:{})});const data=await r.json();if(!r.ok)throw new Error(data.error||'本地配置访问失败');return data;}
function fillSettings(data,keepEdits=false){
  for(const [key,id] of Object.entries(configFields)){if(key!=='gemini_model'&&(!keepEdits||!editedConfigFields.has(id)))$(id).value=data[key]||configDefaults[key]||'';}
  const model=data.gemini_model||'';if(!keepEdits||!editedConfigFields.has('model'))$('model').replaceChildren(new Option(model?model.replace('models/','')+' · 已保存':'先加载你的可用模型',model));updateProviderUI();
}
$('done').onclick=async()=>{if(settingsLoading||!settingsLoaded){$('config-status').textContent='尚未成功读取本机配置，请重新打开页面后保存，以免覆盖原有 Key。';return;}$('done').disabled=true;$('clear-config').disabled=true;try{const data=Object.fromEntries(Object.entries(configFields).map(([key,id])=>[key,$(id).value.trim()]));await settingsAPI('POST',data);settingsDirty=false;updateProviderUI();$('config-status').textContent='已保存到本机，刷新后会自动恢复。';$('dialog').close();status('API 配置已保存 · 当前写作服务：'+$('writer-status').textContent);}catch(e){$('config-status').textContent='保存失败：'+e.message;}finally{$('done').disabled=false;$('clear-config').disabled=false;}};
$('clear-config').onclick=async()=>{if(!confirm('清除本机保存的全部 API Key 和模型配置？稿件和对话不受影响。'))return;$('clear-config').disabled=true;$('done').disabled=true;try{await settingsAPI('POST',{});fillSettings({});settingsDirty=false;$('config-status').textContent='已清除本机保存的配置。';}catch(e){$('config-status').textContent=e.message;}finally{$('clear-config').disabled=false;$('done').disabled=false;}};
(async()=>{try{const data=await settingsAPI('GET');settingsLoaded=true;{fillSettings(data.settings,true);$('config-status').textContent=data.settings.gemini_key||data.settings.openai_key||data.settings.gcp_key?'已自动加载本机配置，原有 Key 已保留。':'填写后点击“保存配置”，以后无需重复输入。';}}catch(e){$('config-status').textContent='未能加载配置：'+e.message;}finally{settingsLoading=false;}})();
