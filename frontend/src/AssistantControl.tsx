import {useEffect,useState} from 'react';
import {api} from './api';
import {setupHint,type AssistantConfiguration} from './assistantProvider';
import {MODEL_OPTIONS,EFFORT_OPTIONS,MODEL_SETTINGS_KEY,decodeModelSelection,requestModelOptions,type ModelSelection,type Provider} from './modelSettings';

export function useAssistantConfiguration(provider?:Provider){
 const [status,setStatus]=useState<AssistantConfiguration|null>(null),[cycle,setCycle]=useState(0);
 useEffect(()=>{let active=true;void api<AssistantConfiguration>('/assistant/status'+(provider?'?provider='+encodeURIComponent(provider):'')).then(v=>{if(active)setStatus(v);}).catch(()=>{if(active)setStatus(null);});return()=>{active=false;};},[cycle,provider]);
 return {status:provider&&status?.provider!==provider?null:status,refresh:()=>setCycle(v=>v+1)};
}

const CHANGE_EVENT='gold-desk-model-selection-change';
const savedSelection=()=>{try{return decodeModelSelection(localStorage.getItem(MODEL_SETTINGS_KEY));}catch{return decodeModelSelection(null);}};
export type AssistantSettings={status:AssistantConfiguration|null;refresh:()=>void;selection:ModelSelection;update:(patch:Partial<ModelSelection>)=>void;requestOptions:Partial<ModelSelection>};
export function useAssistantSettings():AssistantSettings{
 const [selection,setSelection]=useState(savedSelection);const {status,refresh}=useAssistantConfiguration(selection.provider);
 useEffect(()=>{const sync=(event:Event)=>setSelection(event.type==='storage'?savedSelection():decodeModelSelection(JSON.stringify((event as CustomEvent).detail)));window.addEventListener(CHANGE_EVENT,sync);window.addEventListener('storage',sync);return()=>{window.removeEventListener(CHANGE_EVENT,sync);window.removeEventListener('storage',sync);};},[]);
 const update=(patch:Partial<ModelSelection>)=>{const next=decodeModelSelection(JSON.stringify({...selection,...patch}));setSelection(next);try{localStorage.setItem(MODEL_SETTINGS_KEY,JSON.stringify(next));}catch{/* keep this session usable */}window.dispatchEvent(new CustomEvent(CHANGE_EVENT,{detail:next}));};
 return {status,refresh,selection,update,requestOptions:requestModelOptions(status,selection)};
}

export default function AssistantControl({settings,busy=false}:{settings:AssistantSettings;busy?:boolean}){
 const {status,refresh,selection,update}=settings,ready=Boolean(status?.configured&&status.enabled),provider=selection.provider??status?.provider??'claude_code',claude=provider==='claude_code';
 const chosen=status?.models?.find(m=>m.id===selection.codex_model)??status?.models?.find(m=>m.id===status.model)??status?.models?.[0];
 return <div className="assistant-model-controls" role="group" aria-label="模型與思考程度"><label>助手<select aria-label="AI供應商" value={provider} disabled={busy} onChange={e=>update({provider:e.target.value as Provider})}><option value="claude_code">Claude Code</option><option value="codex">Codex</option><option value="program">程式解讀</option><option value="openai_compatible">API／Groq</option></select></label>
 {provider==='codex'?<><label>模型<select aria-label="模型" disabled={busy||!chosen} value={chosen?.id??''} onChange={e=>{const m=status?.models?.find(m=>m.id===e.target.value);if(m)update({codex_model:m.id,codex_effort:m.default_effort});}}>{!chosen&&<option value="">尚未就緒</option>}{status?.models?.map(m=><option key={m.id} value={m.id}>{m.label}</option>)}</select></label><label>思考程度<select aria-label="思考程度" disabled={busy||!chosen} value={chosen?.efforts.includes(selection.codex_effort??'')?selection.codex_effort:chosen?.default_effort??''} onChange={e=>update({codex_effort:e.target.value})}>{!chosen&&<option value="">尚未就緒</option>}{chosen?.efforts.map(v=><option key={v} value={v}>{EFFORT_OPTIONS.find(o=>o.id===v)?.label??v}</option>)}</select></label></>:claude?<><label>模型<select aria-label="模型" value={status?selection.model:''} disabled={busy||!status} onChange={e=>update({model:e.target.value as ModelSelection['model']})}>{!status&&<option value="">讀取中</option>}{MODEL_OPTIONS.map(o=><option key={o.id} value={o.id}>{o.label}</option>)}</select></label>
 <label>思考程度<select aria-label="思考程度" value={status?selection.effort:''} disabled={busy||!status} onChange={e=>update({effort:e.target.value as ModelSelection['effort']})}>{!status&&<option value="">讀取中</option>}{EFFORT_OPTIONS.map(o=><option key={o.id} value={o.id}>{o.label}</option>)}</select></label></>:<small>{status?.model}</small>}
 <details className="fine"><summary>連線設定{status?.reason==='authentication_required'?' · 尚未登入':!ready?' · 未就緒':''}</summary><p>{setupHint(status)}</p><p>程度為本次請求設定；較高程度可能需要較久，模型與帳戶政策可能限制實際程度。</p><button type="button" disabled={busy} onClick={refresh}>重新檢查連線</button></details></div>;
}
