export const MODEL_OPTIONS=[{id:'sonnet',label:'Sonnet'},{id:'opus',label:'Opus'},{id:'haiku',label:'Haiku'}] as const;
export const EFFORT_OPTIONS=[{id:'low',label:'快速'},{id:'medium',label:'標準'},{id:'high',label:'深入'},{id:'xhigh',label:'更深入'},{id:'max',label:'最高'}] as const;
export type Provider='claude_code'|'codex'|'program'|'openai_compatible';
export type ModelSelection={model:typeof MODEL_OPTIONS[number]['id'];effort:typeof EFFORT_OPTIONS[number]['id'];provider?:Provider;codex_model?:string;codex_effort?:string};
export const MODEL_SETTINGS_KEY='gold-desk-claude-selection-v1';
export const requestModelOptions=(status:AssistantConfiguration|null,selection:ModelSelection):Partial<ModelSelection>=>{
 const provider=selection.provider??status?.provider;
 if(provider==='codex'){
  const chosen=status?.models?.find(m=>m.id===selection.codex_model)??status?.models?.find(m=>m.id===status.model)??status?.models?.[0];
  return {provider:'codex',...(chosen?{codex_model:chosen.id,codex_effort:chosen.efforts.includes(selection.codex_effort??'')?selection.codex_effort:chosen.default_effort}:{})};
 }
 if(provider==='claude_code')return {model:selection.model,effort:selection.effort,...(selection.provider?{provider:selection.provider}:{})};
 return selection.provider?{provider:selection.provider}:{};
};
export function decodeModelSelection(raw:string|null):ModelSelection{
 try{const v=raw?JSON.parse(raw):null;if(v){const base={model:MODEL_OPTIONS.some(o=>o.id===v.model)?v.model:'sonnet',effort:EFFORT_OPTIONS.some(o=>o.id===v.effort)?v.effort:'medium'};
 if(['claude_code','codex','program','openai_compatible'].includes(v.provider))return {...base,provider:v.provider,...(typeof v.codex_model==='string'&&/^[A-Za-z0-9][A-Za-z0-9._:-]{0,100}$/.test(v.codex_model)?{codex_model:v.codex_model}:{}),...(typeof v.codex_effort==='string'&&['none','minimal','low','medium','high','xhigh','max','ultra'].includes(v.codex_effort)?{codex_effort:v.codex_effort}:{})};
 if(MODEL_OPTIONS.some(o=>o.id===v.model)&&EFFORT_OPTIONS.some(o=>o.id===v.effort))return base;}}catch{/* invalid preferences use defaults */}
 return {model:'sonnet',effort:'medium'};
}
export function selectionLabel(model:string|null|undefined,effort?:string|null):string{
 if(!model)return '';
 const name=MODEL_OPTIONS.find(o=>o.id===model)?.label??model;
 return name+(effort?` · 思考設定：${EFFORT_OPTIONS.find(o=>o.id===effort)?.label??effort}`:'');
}
import type {AssistantConfiguration} from './assistantProvider';
