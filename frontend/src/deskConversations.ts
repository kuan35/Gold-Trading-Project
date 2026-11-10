import type {Side} from './types';
import type {DraftInputState,InputPatch} from './conversationState';
import {validAnalysisRef,normalizeArchivedChart,type ArchivedChart} from './analysisHistory';

export const DESK_HISTORY_KEY='gold-desk-conversations-v1';
export const LIVE_HISTORY_KEY='gold-desk-live-conversations-v1';
export type ArchiveTurn={question:string;answer:string;at:string;analysis_ref?:string};
export type ArchiveEntry={id:string;title:string;updatedAt:number;turns:ArchiveTurn[];customTitle?:boolean;chart?:ArchivedChart};
export type ArchiveLoad={items:ArchiveEntry[];writable:boolean;error:string;activeId?:string};
const MAX_ARCHIVE_CHARS=4_000_000;
const safeText=(value:string,max=Number.MAX_SAFE_INTEGER)=>value.replace(/(?:gsk_|sk-|github_pat_|ghp_)[A-Za-z0-9_-]{12,}/g,'[憑證已隱藏]').slice(0,max);
const record=(value:unknown):value is Record<string,unknown>=>Boolean(value&&typeof value==='object'&&!Array.isArray(value));
const normalizeTurn=(value:unknown):ArchiveTurn|null=>{
 if(!record(value)||typeof value.question!=='string'||typeof value.answer!=='string'||typeof value.at!=='string'||!Number.isFinite(Date.parse(value.at)))return null;
 return {question:safeText(value.question,1500),answer:safeText(value.answer),at:value.at,...(validAnalysisRef(value.analysis_ref)?{analysis_ref:value.analysis_ref}:{})};
};
export function makeArchiveEntry(id:string,turns:ArchiveTurn[],updatedAt:number,chart?:ArchivedChart):ArchiveEntry{
 const rows=turns.map(normalizeTurn).filter((v):v is ArchiveTurn=>v!==null);
 const savedChart=normalizeArchivedChart(chart,rows.flatMap(t=>t.analysis_ref?[t.analysis_ref]:[]));
 return {id:id.slice(0,80),title:safeText(turns[0]?.question||'交易討論',24),updatedAt,turns:rows,...(savedChart?{chart:savedChart}:{})};
}
export function mergeArchive(previous:ArchiveEntry[],entry:ArchiveEntry):ArchiveEntry[]{
 const saved=previous.find(v=>v.id===entry.id),chart=normalizeArchivedChart(entry.chart??saved?.chart,entry.turns.flatMap(t=>t.analysis_ref?[t.analysis_ref]:[]));
 const next={...entry,...(saved?.customTitle?{title:saved.title,customTitle:true}:{}),...(chart?{chart}:{})};
 return [...previous.filter(v=>v.id!==entry.id),next].filter(v=>v.turns.length).sort((a,b)=>b.updatedAt-a.updatedAt||a.id.localeCompare(b.id));
}
export function renameConversation(items:ArchiveEntry[],id:string,title:string):ArchiveEntry[]{
 const name=safeText(title.trim(),48);if(!name)throw Error('請輸入對話名稱。');
 return items.map(item=>item.id===id?{...item,title:name,customTitle:true}:item);
}
export const deleteConversation=(items:ArchiveEntry[],id:string)=>items.filter(item=>item.id!==id);
export function decodeArchive(raw:string|null):ArchiveLoad{
 if(raw===null)return {items:[],writable:true,error:''};
 const error={items:[],writable:false,error:'無法讀取已保存的對話，本次不覆寫原紀錄。'};
 try{
  if(raw.length>MAX_ARCHIVE_CHARS)return error;
  const value:unknown=JSON.parse(raw);
  if(!record(value)||![1,2,3].includes(value.version as number)||!Array.isArray(value.items))return error;
  if(value.activeId!==undefined&&(typeof value.activeId!=='string'||!value.activeId||value.activeId.length>80))return error;
  const items:ArchiveEntry[]=[];const ids=new Set<string>();
  for(const row of value.items){
   if(!record(row)||typeof row.id!=='string'||!row.id||row.id.length>80||ids.has(row.id)||typeof row.title!=='string'||typeof row.updatedAt!=='number'||!Number.isFinite(row.updatedAt)||!Array.isArray(row.turns))return error;
   const turns=row.turns.map(normalizeTurn);if(turns.some(t=>t===null))return error;
   if(row.customTitle!==undefined&&typeof row.customTitle!=='boolean')return error;
   const chart=normalizeArchivedChart(row.chart,(turns as ArchiveTurn[]).flatMap(t=>t.analysis_ref?[t.analysis_ref]:[]));
   ids.add(row.id);items.push({id:row.id,title:safeText(row.title,48),updatedAt:row.updatedAt,turns:turns as ArchiveTurn[],...(row.customTitle?{customTitle:true}:{}),...(chart?{chart}:{})});
  }
  return {items:items.sort((a,b)=>b.updatedAt-a.updatedAt),writable:true,error:'',...(typeof value.activeId==='string'?{activeId:value.activeId}:{})};
 }catch{return error;}
}
export function encodeArchive(items:ArchiveEntry[],activeId?:string):string{
 const value=JSON.stringify({version:3,...(activeId?{activeId}:{}),items:items.map(row=>({...makeArchiveEntry(row.id,row.turns,row.updatedAt,row.chart),title:safeText(row.title,48),...(row.customTitle?{customTitle:true}:{})}))});
 if(value.length>MAX_ARCHIVE_CHARS)throw Error('對話儲存空間不足，本次變更未儲存；請先備份或刪除不需要的紀錄。');
 return value;
}
export function saveConversationArchive(storage:Pick<Storage,'setItem'>,items:ArchiveEntry[],activeId:string,storageKey=DESK_HISTORY_KEY):{ok:boolean;error:string}{
 try{storage.setItem(storageKey,encodeArchive(items,activeId));return {ok:true,error:''};}
 catch{return {ok:false,error:'這次變更未儲存，先前已保存的紀錄仍保留。請確認瀏覽器允許儲存，或備份後刪除不需要的紀錄。'};}
}
export function persistConversationDeletion(storage:Pick<Storage,'setItem'>,items:ArchiveEntry[],id:string,activeId:string,storageKey=DESK_HISTORY_KEY){
 const remaining=deleteConversation(items,id),result=saveConversationArchive(storage,remaining,activeId,storageKey);
 const keep=new Set(remaining.flatMap(e=>e.turns.flatMap(t=>t.analysis_ref?[t.analysis_ref]:[])));
 const refs=[...new Set(items.find(e=>e.id===id)?.turns.flatMap(t=>t.analysis_ref?[t.analysis_ref]:[])??[])];
 return {...result,items:remaining,cleanupRefs:result.ok?refs.filter(ref=>!keep.has(ref)):[]};
}
export function needsAnalysis(intent:string,patch:InputPatch,before:Side|null,after:Side|null,hasAnalysis:boolean):boolean{
 if(intent==='DISCUSS')return true;
 if(intent!=='PREPARE'&&intent!=='EDIT')return false;
 return Boolean(after&&((patch.side&&after!==before)||(intent==='PREPARE'&&!hasAnalysis)));
}
export function changedFields(before:DraftInputState,after:DraftInputState):string[]{
 const labels:Record<keyof DraftInputState,string>={side:'方向',order_type:'單型',lot:'手數',limit_price:'限價',sl:'停損',tp:'停利'};
 const display=(v:string|null)=>({BUY:'做多',SELL:'做空',MARKET:'市價',LIMIT:'限價'}[v??'']||v||'未設定');
 return (Object.keys(labels) as (keyof DraftInputState)[]).filter(k=>before[k]!==after[k]).map(k=>`${labels[k]} ${display(before[k])} → ${display(after[k])}`);
}
