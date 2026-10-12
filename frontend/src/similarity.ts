/** Structured operation matching. No outcome is consulted until pool summary. */
import Decimal from 'decimal.js';
import type {Action,Case,Retrieval,Side} from './types';
type Item=Case&{available_at:number;prior_count?:number;prior_lot?:string;signed_distance?:string|null;typical_lot?:string|null};
type Query={side:Side;action:Action;lot:string;clock:number;prior_count:number;prior_lot:string;signed_distance:string|null;typical_lot?:string|null};
const d=(v:Decimal.Value)=>new Decimal(v);
const gap=(a:Decimal,b:Decimal)=>Math.abs(Math.log2(b.toNumber())-Math.log2(a.toNumber()));
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
 const qty=valid(q.lot),typical=q.typical_lot?valid(q.typical_lot):null;
 if(!qty||(q.typical_lot&&!typical))throw Error('手數與平常手數必須大於零且有限');
 const ranked:Case[]=[];
 for(const c of items){
  if(c.side!==q.side||c.action!==q.action||c.available_at>q.clock)continue;
  const ref=valid(c.typical_lot);if(typical&&!ref)continue;
  const querySize=typical?qty.div(typical):qty,caseSize=typical?d(c.lot).div(ref!):d(c.lot);
  const sizeGap=gap(querySize,caseSize);if(sizeGap>1+1e-12)continue;
  const components:NonNullable<Case['components']>=[],missing:string[]=[],reasons=['買賣方向相同',q.action==='FIRST'?'同為可見首筆':'同為同向加倉'];
  const differences=['合成示範；未納入盤面相似度',typical?'平常手數僅取案例當時之前的示範紀錄':'未提供平常手數；僅比較絕對手數'];
  const add=(feature:string,label:string,query:Decimal|null,value:Decimal|null,weight:number,distance:number|null)=>{
   components.push({feature,label,query:query?.toString()??null,case:value?.toString()??null,weight,distance:distance??1,missing:distance===null});
   if(distance===null){missing.push(feature);differences.push(`${label}資料不足；保留缺值懲罰`);}
   else (distance<=.25?reasons:differences).push(`${label}：本次 ${query}／案例 ${value}`);
  };
  add('lot',typical?'相對平常手數倍數':'下單手數',querySize,caseSize,q.action==='FIRST'?1:.35,sizeGap);
  if(q.action==='ADD'){
   add('prior_count','既有同向單數',d(q.prior_count),c.prior_count===undefined?null:d(c.prior_count),.2,c.prior_count===undefined?null:Math.min(Math.abs(c.prior_count-q.prior_count)/Math.max(c.prior_count,q.prior_count,1),1));
   const prior=valid(q.prior_lot),cp=valid(c.prior_lot),a=prior?qty.div(prior):null,b=cp?d(c.lot).div(cp):null,eg=a&&b?gap(a,b):null;
   if(eg!==null&&eg>1+1e-12)continue;
   add('exposure_ratio','加單占既有部位倍數',a,b,.25,eg);
   const qs=q.signed_distance!==null?d(q.signed_distance):null,cs=c.signed_distance!=null?d(c.signed_distance):null;
   if(qs&&cs&&qs.abs().gt('.02')&&cs.abs().gt('.02')&&qs.times(cs).lt(0))continue;
   const sg=qs&&cs?cs.minus(qs).abs().div('.5').toNumber():null;if(sg!==null&&sg>1)continue;
   add('signed_distance','方向調整後距均價百分比',qs,cs,.2,sg);
  }
  const distance=components.reduce((n,c)=>n+c.weight*c.distance,0);if(distance>.65)continue;
  const {typical_lot:_,...safe}=c;
  ranked.push({...safe,operation_distance:Number(distance.toFixed(6)),operation_comparison:{distance:Number(distance.toFixed(6)),label:'操作條件接近',strength:q.action==='FIRST'?'weak':'limited',reason:q.action==='FIRST'?'首筆只比較方向、可見首筆與手數；辨識力有限':'比較手數與既有部位條件'},market_comparison:{status:'unavailable',label:'盤面尚無法比較',distance:null,coverage:0,components:[],reason:'Pages合成案例未附歷史盤面特徵；未進行盤面匹配'},distance:Number(distance.toFixed(6)),comparison_basis:typical?'relative_lot':'absolute_lot',components,missing_features:missing,match_reasons:reasons,differences});
 }
 const seen=new Set<string>();return ranked.sort((a,b)=>Number(a.distance)-Number(b.distance)||a.id.localeCompare(b.id)).filter(c=>{if(seen.has(c.group))return false;seen.add(c.group);return true;});
}

export function summarizeCases(ranked:Case[],typical?:string|null,excluded=0):Retrieval{
 const profit=ranked.filter(c=>d(c.profit).gt(0)),loss=ranked.filter(c=>d(c.profit).lt(0));
 const chosen=new Set([...profit.slice(0,3),...loss.slice(0,3)].map(c=>c.id));
 for(const c of ranked){if(chosen.size>=6)break;chosen.add(c.id);}
 const reasons=['合成資料僅供流程展示，不能代表真實交易證據','相似度權重與門檻尚未完成相關性驗證','尚無盤面比較證據'];
 if(ranked.length<30)reasons.push('相似候選群少於30');if(!typical)reasons.push('未比較相對平常手數');
 return {total:ranked.length,wins:profit.length,losses:loss.length,flat:ranked.length-profit.length-loss.length,unknown:0,
  win_rate:ranked.length?d(profit.length).div(ranked.length).times(100).toFixed(1):null,cases:ranked.filter(c=>chosen.has(c.id)),profit_cases:profit.slice(0,6),loss_cases:loss.slice(0,6),
  comparison:{mode:'operation_only',market_matches:0,operation_candidates:ranked.length,verified_market_candidates:0,excluded_unverified_market:0,reason:'Pages合成案例僅比較操作條件；盤面尚無法比較',method:'operation_context_20261012',basis:typical?'relative_lot':'absolute_lot',max_distance:.65,excluded_missing_profile:excluded,market_features_enabled:false,parameters_validated:false},
  sufficiency:{status:ranked.length<5?'insufficient':'limited',label:ranked.length<5?'資料不足':'有限參考',reasons,matched_groups:ranked.length,is_success_probability:false},
  limitations:['全部合成案例，比例不代表交易員績效或本次預測勝率','先形成完整匹配池，再並列最相似的獲利與虧損案例','目前只比較操作條件，未啟用盤面相似度']};
}
