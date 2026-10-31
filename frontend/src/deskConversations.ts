import type {Side} from './types';
import type {DraftInputState,InputPatch} from './conversationState';

export const DESK_HISTORY_KEY='gold-desk-conversations-v1';
export type ArchiveTurn={question:string;answer:string;at:string};
export type ArchiveEntry={id:string;title:string;updatedAt:number;turns:ArchiveTurn[];customTitle?:boolean};
type ArchiveLoad={items:ArchiveEntry[];writable:boolean;error:string};
const safeText=(value:string,max:number)=>value.replace(/(?:gsk_|sk-|github_pat_|ghp_)[A-Za-z0-9_-]{12,}/g,'[憑證已隱藏]').slice(0,max);
const record=(value:unknown):value is Record<string,unknown>=>Boolean(value&&typeof value==='object'&&!Array.isArray(value));
const normalizeTurn=(value:unknown):ArchiveTurn|null=>{
 if(!record(value)||typeof value.question!=='string'||typeof value.answer!=='string'||typeof value.at!=='string'||!Number.isFinite(Date.parse(value.at)))return null;
 return {question:safeText(value.question,1500),answer:safeText(value.answer,1800),at:value.at};
};
export function makeArchiveEntry(id:string,turns:ArchiveTurn[],updatedAt:number):ArchiveEntry{
 const rows=turns.slice(-20).map(normalizeTurn).filter((v):v is ArchiveTurn=>v!==null);
 return {id:id.slice(0,80),title:safeText(turns[0]?.question||'交易討論',24),updatedAt,turns:rows};
}
export function mergeArchive(previous:ArchiveEntry[],entry:ArchiveEntry):ArchiveEntry[]{
 const saved=previous.find(v=>v.id===entry.id);const next=saved?.customTitle?{...entry,title:saved.title,customTitle:true}:entry;
 return [...previous.filter(v=>v.id!==entry.id),next].filter(v=>v.turns.length).sort((a,b)=>b.updatedAt-a.updatedAt||a.id.localeCompare(b.id)).slice(0,12);
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
  if(raw.length>1_200_000)return error;
  const value:unknown=JSON.parse(raw);
  if(!record(value)||value.version!==1||!Array.isArray(value.items)||value.items.length>12)return error;
  const items:ArchiveEntry[]=[];const ids=new Set<string>();
  for(const row of value.items){
   if(!record(row)||typeof row.id!=='string'||!row.id||row.id.length>80||ids.has(row.id)||typeof row.title!=='string'||typeof row.updatedAt!=='number'||!Number.isFinite(row.updatedAt)||!Array.isArray(row.turns)||row.turns.length>20)return error;
   const turns=row.turns.map(normalizeTurn);if(turns.some(t=>t===null))return error;
   if(row.customTitle!==undefined&&typeof row.customTitle!=='boolean')return error;
   ids.add(row.id);items.push({id:row.id,title:safeText(row.title,48),updatedAt:row.updatedAt,turns:turns as ArchiveTurn[],...(row.customTitle?{customTitle:true}:{})});
  }
  return {items:items.sort((a,b)=>b.updatedAt-a.updatedAt),writable:true,error:''};
 }catch{return error;}
}
export function encodeArchive(items:ArchiveEntry[]):string{
 return JSON.stringify({version:1,items:items.slice(0,12).map(row=>({...makeArchiveEntry(row.id,row.turns,row.updatedAt),title:safeText(row.title,48),...(row.customTitle?{customTitle:true}:{})}))});
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
