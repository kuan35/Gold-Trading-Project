import Decimal from 'decimal.js';
import type {Side,OrderType} from './types';
export type DraftInputState={side:Side|null;order_type:OrderType|null;lot:string;limit_price:string;sl:string;tp:string};
export type InputPatch=Partial<{[K in keyof DraftInputState]:DraftInputState[K]|null}>;
export const emptyInput=():DraftInputState=>({side:null,order_type:null,lot:'',limit_price:'',sl:'',tp:''});
export function patchInput(input:DraftInputState,patch:InputPatch):DraftInputState{
 const next={...input};
 for(const field of ['side','order_type','lot','limit_price','sl','tp'] as const){
  if(!(field in patch))continue;
  const value=patch[field];
  if(field==='side'){if(value==='BUY'||value==='SELL'||value===null)next.side=value;}
  else if(field==='order_type'){if(value==='MARKET'||value==='LIMIT'||value===null)next.order_type=value;}
  else if(value===null||typeof value==='string')next[field]=value??'';
 }
 return next;
}
const positive=(s:string)=>{try{const n=new Decimal(s);return n.isFinite()&&n.gt(0);}catch{return false;}};
export function missingInput(input:DraftInputState):string[]{
 return [...(!input.side?['方向']:[]),...(!input.order_type?['單型']:[]),...(!positive(input.lot)?['手數']:[]),...(input.order_type==='LIMIT'&&!positive(input.limit_price)?['限價']:[])];
}
export const acceptRevision=(sent:number,current:number)=>sent===current;
export const discussionSide=(explicit:Side|null,input:Side|null,previous:Side|null):Side|null=>explicit??input??previous;
export function submissionLocked(status:string,observed?:string,accountUpdated?:string):boolean{
 if(['REJECTED','CANCELLED','EXPIRED','MISSED'].includes(status))return false;
 if(status!=='FILLED')return true;
 const last=Date.parse(observed??''),account=Date.parse(accountUpdated??'');
 return !Number.isFinite(last)||!Number.isFinite(account)||account<=last;
}
