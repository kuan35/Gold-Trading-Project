/** Structured operation matching. No outcome is consulted until pool summary. */
import Decimal from 'decimal.js';
import type {Action,Case,Retrieval,Side} from './types';
type Item=Case&{available_at:number;prior_count?:number;prior_lot?:string;signed_distance?:string|null;typical_lot?:string|null};
type Query={side:Side;action:Action;lot:string;clock:number;prior_count:number;prior_lot:string;signed_distance:string|null;typical_lot?:string|null};
const d=(v:Decimal.Value)=>new Decimal(v);
const valid=(v?:string|null)=>{if(!v)return null;try{const n=d(v);return n.isFinite()&&n.gt(0)?n:null;}catch{return null;}};

export function attachDemoProfiles(items:Item[]):void{
 const batches=new Map<number,Item[]>();
 for(const c of items){const t=Date.parse(String(c.opened_at))/1000,b=Math.floor(t/300)*300;batches.set(b,[...(batches.get(b)||[]),c]);}
 const previous:{time:number;lot:Decimal}[]=[];
 const median=(values:Decimal[])=>{const a=values.sort((x,y)=>x.cmp(y)),m=Math.floor(a.length/2);return a.length%2?a[m]:a[m-1].plus(a[m]).div(2);};
 for(const [time,group] of [...batches].sort((a,b)=>a[0]-b[0])){
  const past=previous.slice(-20),days=new Set(past.map(p=>Math.floor(p.time/86400))).size;
  const baseline=past.length>=10&&days>=3?median(past.map(p=>p.lot)).toString():null;
  group.forEach(c=>{c.typical_lot=baseline;});
  const earliest=Math.min(...group.map(c=>Date.parse(String(c.opened_at))));
  previous.push({time,lot:median(group.filter(c=>Date.parse(String(c.opened_at))===earliest).map(c=>d(c.lot)))});
 }
}

export function rankCases(items:Item[],q:Query):Case[]{
 if(!valid(q.lot)||(q.typical_lot&&!valid(q.typical_lot)))throw Error('手數與平常手數必須大於零且有限');
 const ranked=items.filter(c=>c.side===q.side&&c.available_at<=q.clock)
  .sort((a,b)=>a.id.localeCompare(b.id));
 const seen=new Set<string>();
 return ranked.filter(c=>{if(seen.has(c.group))return false;seen.add(c.group);return true;})
  .map(c=>{const {typical_lot:_,...safe}=c;return {...safe,distance:null,comparison_basis:'direction_only',
   market_comparison:{status:'unavailable' as const,label:'盤面尚無法比較',distance:null,coverage:0,components:[],reason:'合成案例沒有歷史盤面'},
   match_reasons:['買賣方向相同'],differences:['合成案例沒有已核實的歷史盤面比較']};});
}

export function summarizeCases(ranked:Case[],typical?:string|null,excluded=0):Retrieval{
 const profit=ranked.filter(c=>d(c.profit).gt(0)),loss=ranked.filter(c=>d(c.profit).lt(0));
 const chosen=new Set([...profit.slice(0,3),...loss.slice(0,3)].map(c=>c.id));
 for(const c of ranked){if(chosen.size>=6)break;chosen.add(c.id);}
 const reasons=['合成資料僅供流程展示，不能代表真實交易證據','只依買賣方向列出案例；沒有歷史盤面相似度'];
 if(ranked.length<30)reasons.push('相似候選群少於30');
 return {total:ranked.length,wins:profit.length,losses:loss.length,flat:ranked.length-profit.length-loss.length,unknown:0,
  win_rate:ranked.length?d(profit.length).div(ranked.length).times(100).toFixed(1):null,cases:ranked.filter(c=>chosen.has(c.id)),profit_cases:profit.slice(0,6),loss_cases:loss.slice(0,6),
  comparison:{mode:'operation_only',market_matches:0,operation_candidates:ranked.length,verified_market_candidates:0,excluded_unverified_market:0,reason:'合成示範・僅依方向列出案例，沒有歷史盤面相似度',method:'synthetic_direction_only',basis:'direction_only',max_distance:null,excluded_missing_profile:excluded,market_features_enabled:false,parameters_validated:false},
  sufficiency:{status:ranked.length<5?'insufficient':'limited',label:ranked.length<5?'資料不足':'有限參考',reasons,matched_groups:ranked.length,is_success_probability:false},
  limitations:['全部合成案例，比例不代表交易員績效或本次預測勝率','只依買賣方向列出案例，盈虧不參與排序','沒有歷史盤面相似度']};
}
