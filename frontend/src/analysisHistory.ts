import type {MarketReply} from './LiveAssistant';
export type ArchivedChart={id:string;analysis_ref?:string;mode:'analysis'|'cases';period?:'5m'|'15m'|'1h';selection?:{caseRef:string;minutes?:5|30|60}};
export const validAnalysisRef=(value:unknown):value is string=>typeof value==='string'&&/^[0-9a-f]{64}$/.test(value);
const object=(v:unknown):v is Record<string,unknown>=>Boolean(v&&typeof v==='object'&&!Array.isArray(v));
export function normalizeArchivedChart(value:unknown,refs:string[]):ArchivedChart|undefined{
 if(!object(value)||!validAnalysisRef(value.id)||!validAnalysisRef(value.analysis_ref)||!refs.includes(value.analysis_ref)||!['analysis','cases'].includes(String(value.mode)))return;
 const result:ArchivedChart={id:value.id,analysis_ref:value.analysis_ref,mode:value.mode as ArchivedChart['mode']};
 if(['5m','15m','1h'].includes(String(value.period)))result.period=value.period as ArchivedChart['period'];
 const s=value.selection;
 if(object(s)&&typeof s.caseRef==='string'&&s.caseRef.length>0&&s.caseRef.length<=64){
  result.selection={caseRef:s.caseRef,...([5,30,60].includes(s.minutes as number)?{minutes:s.minutes as 5|30|60}:{})};
 }
 return result;
}
export async function loadAnalysis(ref:string,{signal,fetcher=fetch}:{signal?:AbortSignal;fetcher?:(url:string,options?:RequestInit)=>Promise<Response>}={}):Promise<MarketReply>{
 if(!validAnalysisRef(ref))throw Error('歷史分析編號無效。');
 const response=await fetcher('/api/assistant/analyses/'+ref,{signal});
 if(!response.ok)throw Error('原分析副本暫時無法讀取，以下保留舊文字；沒有重新分析。');
 const r:unknown=await response.json();
 if(!object(r)||r.analysis_ref!==ref)throw Error('歷史分析編號不一致，未顯示其他分析。');
 if(r.draft!==null||'draft_id' in r||'idempotency_key' in r)throw Error('歷史回覆不是唯讀分析，未載入。');
 if(!Array.isArray(r.sections)||!Array.isArray(r.evidence)||!Array.isArray(r.followups)||typeof r.as_of_utc!=='string'||typeof r.provider!=='string'||typeof r.market_status!=='string'||typeof r.message!=='string'||r.sections.some(s=>!object(s)||typeof s.title!=='string'||typeof s.text!=='string'||!Array.isArray(s.fact_ids)))throw Error('歷史分析格式不完整，以下保留舊文字。');
 return r as MarketReply;
}
export class ConversationSessions<T extends {proposal?:unknown;proposalRevision?:number}>{
 private items=new Map<string,{turns:T[];chart:ArchivedChart|null}>();
 save(id:string,turns:T[],chart:ArchivedChart|null){this.items.set(id,{turns:turns.map(t=>{const {proposal,proposalRevision,...safe}=t;return safe as T;}),chart});}
 get(id:string){return this.items.get(id);}
 delete(id:string){this.items.delete(id);}
}
