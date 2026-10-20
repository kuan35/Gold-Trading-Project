/** Public Pages sandbox: synthetic replay and explicitly released real case archive. */
import Decimal from 'decimal.js';
import {validateRules,evaluateRules,parseRuleMessage,type PersonalRule} from './personalRules';
import {tradeChart} from './tradeChart';
import fixtures from './demo-data.json';
import {attachDemoProfiles,rankCases,summarizeCases} from './similarity';
import {loadPublicHistory,PublicHistoryStore} from './publicHistory';
import type {Action,Audit,Bar,BarsResponse,Case,Draft,Order,OrderType,PendingOrder,Position,Retrieval,Side,State} from './types';
Decimal.set({precision:28,rounding:Decimal.ROUND_HALF_EVEN});
const d=(v:Decimal.Value)=>new Decimal(v);
const money=(v:Decimal.Value)=>d(v).toFixed(2);
const sum=(values:Decimal.Value[])=>values.reduce<Decimal>((a,b)=>a.plus(b),d(0));
const id=()=>crypto.randomUUID();
type SourceBar={time:number;open:string;high:string;low:string;close:string;volume:number};
type DemoCase=Case & {available_at:number;prior_count:number;prior_lot?:string;typical_lot?:string|null;signed_distance:string|null};
type Receipt={status:string;order_id:string;state:State};
const source='合成行情示範・GitHub Pages 瀏覽器回放・非即時報價';
const labels:Record<string,string>={NO_OBSERVED_POSITION:'可見初始單',ADD_ADVERSE:'價格不利時加單',ADD_FAVORABLE:'價格有利時加單'};
function quantity(raw:string):Decimal{
 try{const v=d(raw);if(!v.isFinite()||v.lte(0))throw Error();return v;}
 catch{throw Error('請輸入大於零的有效數字');}
}

export class DemoEngine {
 readonly bars=structuredClone(fixtures.bars) as SourceBar[];
 readonly cases=structuredClone(fixtures.cases) as unknown as DemoCase[];
 mode:State['mode']='replay';cursor=360;version=0;balance=d(10000);
 history:PublicHistoryStore|null=null;
 positions:Position[]=[];orders:Order[]=[];pendingOrders:PendingOrder[]=[];drafts=new Map<string,Draft>();
 private confirmations=new Map<string,Receipt>();private closes=new Map<string,Receipt>();
 constructor(){this.reset();this.cases.forEach(c=>{c.currency='USD';});attachDemoProfiles(this.cases);}
 get clock(){return this.bars[this.cursor-1].time+300;}
 reset():State{this.cursor=360;this.balance=d(10000);this.positions=[];this.orders=[];this.pendingOrders=[];this.drafts.clear();this.confirmations.clear();this.closes.clear();this.version++;return this.state();}
 private connected(){if(this.mode!=='replay')throw Error('券商模擬帳戶未連線；GitHub Pages 僅提供瀏覽器示範，請切回歷史回放');}
 quote(){const bid=d(this.bars[this.cursor-1].close);return {bid:money(bid),ask:money(bid.plus('.30')),time:this.clock};}
 private pnl(p:Position):Decimal{return d(this.quote()[p.side==='BUY'?'bid':'ask']).minus(p.entry).times(p.lot).times(100).times(p.side==='BUY'?1:-1);}
 state():State{
  const recent=this.bars.slice(this.cursor-60,this.cursor),close=d(recent.at(-1)!.close);
  const high=Decimal.max(...recent.map(b=>b.high)),low=Decimal.min(...recent.map(b=>b.low));
  return {mode:this.mode,version:this.version,clock:this.clock,data_source:source,broker_connected:false,llm_enabled:false,quote:this.quote(),
   account:{balance:money(this.balance),equity:money(this.balance.plus(sum(this.positions.map(p=>this.pnl(p)))))},
   positions:this.positions.map(p=>({...p,pnl:money(this.pnl(p))})),orders:structuredClone(this.orders).reverse(),pending_orders:structuredClone(this.pendingOrders),
   market:{high:money(high),low:money(low),change_pct:money(close.minus(recent[0].open).div(recent[0].open).times(100)),range_pct:money(high.minus(low).div(close).times(100)),
    ma20:money(sum(recent.slice(-20).map(b=>b.close)).div(20)),ma60:money(sum(recent.map(b=>b.close)).div(60))},
   data_quality:[this.history?'回放行情與成交為合成示範；檢索案例為真實交易員紀錄，兩者來源不同':'GitHub Pages 公開展示：目前僅載入合成資料',
    '瀏覽器記憶體工作階段；重新整理或重設會清空模擬持倉，每位訪客獨立',
    '固定價差0.30美元、100oz/lot；佣金、隔夜費、保證金與強制平倉未模擬',
    this.history?'本地規則解析；無券商連線。真實案例依同方向、已成熟時間、K 線路徑與指標排序':'本地規則解析；無外部 LLM、無券商連線，案例只比較操作條件']};
 }
 action(side:Side):Action{return !this.positions.length?'FIRST':this.positions.every(p=>p.side===side)?'ADD':'OPPOSITE';}
 chart(interval:'5m'|'15m'|'1h'='5m',focus?:string):BarsResponse{
  const seconds={'5m':300,'15m':900,'1h':3600}[interval];if(!seconds)throw Error('不支援的K線週期');
  const buckets=new Map<number,SourceBar[]>();
  for(const b of this.bars.slice(0,this.cursor)){const start=Math.floor(b.time/seconds)*seconds;if(start+seconds>this.clock)continue;buckets.set(start,[...(buckets.get(start)||[]),b]);}
  const bars:Bar[]=[];
  for(const [time,group] of buckets){
   if(group.length!==seconds/300||group.some((b,i)=>b.time!==time+i*300))continue;
   bars.push({time,open:Number(group[0].open),high:Number(Decimal.max(...group.map(b=>b.high))),low:Number(Decimal.min(...group.map(b=>b.low))),close:Number(group.at(-1)!.close),volume:group.reduce((n,b)=>n+b.volume,0)});
  }
  return tradeChart(bars,this.orders,seconds,source,interval,focus);
 }
 rank(side:Side,action:Action,lot:string,typical_lot?:string|null):Case[]{
  const same=this.positions.filter(p=>p.side===side),total=sum(same.map(p=>p.lot));
  const avg=total.gt(0)?sum(same.map(p=>d(p.lot).times(p.entry))).div(total):null;
  const signed=avg?d(this.quote()[side==='BUY'?'ask':'bid']).minus(avg).div(avg).times(100).times(side==='BUY'?1:-1):null;
  return rankCases(this.cases,{side,action,lot,clock:this.clock,prior_count:same.length,prior_lot:total.toString(),signed_distance:signed?.toString()??null,typical_lot});
 }
 retrieve(side:Side,action:Action,lot:string,typical_lot?:string|null):Retrieval{
  if(this.history)return this.history.retrieve(side,this.cursor);
  const excluded=typical_lot?this.cases.filter(c=>c.side===side&&c.action===action&&c.available_at<=this.clock&&!c.typical_lot).length:0;
  return summarizeCases(this.rank(side,action,lot,typical_lot),typical_lot,excluded);
 }
 draft(side:Side,lot:string,sl?:string|null,tp?:string|null,typical_lot?:string|null,orderType:OrderType='MARKET',limitPrice?:string|null):Draft{
  this.connected();if(!['BUY','SELL'].includes(side))throw Error('請選 BUY 或 SELL');
  const qty=quantity(lot);if(qty.gt(100)||!qty.mod('.01').isZero())throw Error('手數範圍0.01至100，間隔0.01');
  const current=d(this.quote()[side==='BUY'?'ask':'bid']);
  if(!['MARKET','LIMIT'].includes(orderType))throw Error('不支援的委託類型');
  if(orderType==='LIMIT'&&!limitPrice)throw Error('限價單必須輸入限價');
  if(orderType==='MARKET'&&limitPrice)throw Error('市價單不接受限價');
  const price=orderType==='LIMIT'?quantity(limitPrice!):current;
  if(orderType==='LIMIT'){
   if(!price.mod('.01').isZero())throw Error('限價須以0.01為單位');
   if(side==='BUY'&&price.gte(current))throw Error('買進限價須低於目前買進價');
   if(side==='SELL'&&price.lte(current))throw Error('賣出限價須高於目前賣出價');
  }
  const stop=sl?quantity(sl):null,target=tp?quantity(tp):null,sign=side==='BUY'?1:-1;
  if(stop&&stop.minus(price).times(sign).gte(0))throw Error('停損必須在下單價格的不利方向');
  if(target&&target.minus(price).times(sign).lte(0))throw Error('停利必須在下單價格的有利方向');
  const before=sum(this.positions.map(p=>p.lot)),same=this.positions.filter(p=>p.side===side);
  const avg=sum([...same.map(p=>d(p.lot).times(p.entry)),price.times(qty)]).div(sum(same.map(p=>p.lot)).plus(qty));
  const scenarios=[-5,-10,-25].map(n=>{
   const move=d(n).times(sign);let value=move.minus(d('.30').times(sign)).times(qty).times(100).times(sign);
   for(const p of this.positions)value=value.plus(d(this.quote()[p.side==='BUY'?'bid':'ask']).plus(move).minus(p.entry).times(p.lot).times(100).times(p.side==='BUY'?1:-1));
   return {move:money(move),loss:money(value.negated())};
  });
  const warnings=stop?[]:['未設定停損；價格情境不是損失上限'];
  if(orderType==='LIMIT')warnings.push('確認後先待成交；情境依限價試算。回放以K棒高低價判斷觸價，沒有逐筆先後、排隊或同棒停損停利重建。');
  if(this.positions.length){warnings.push('加單增加總部位；均價改善不代表風險降低');if(this.positions.some(p=>!p.sl))warnings.push('既有部位含未設定停損的訂單');}
  if(this.action(side)==='OPPOSITE')warnings.push('反向／混合持倉：回放採逐筆持倉，不能當券商淨額模式');
  const result:Draft={id:id(),revision:this.version,side,lot:qty.toString(),sl:stop?.toString()||null,tp:target?.toString()||null,price:money(price),order_type:orderType,limit_price:orderType==='LIMIT'?money(price):null,action:this.action(side),status:'REVIEW',
   risk:{before_lot:before.toString(),after_lot:before.plus(qty).toString(),average_entry:money(avg),stop_loss_usd:stop?money(price.minus(stop).abs().times(qty).times(100)):null,
    reward_risk:stop&&target?money(target.minus(price).abs().div(stop.minus(price).abs())):null,scenarios,warnings},
   retrieval:this.retrieve(side,this.action(side),lot,typical_lot),explanation:'合成回放與瀏覽器情境試算；案例來源請看檢索說明。請自行核對後確認，尚未成交。'};
  this.drafts.set(result.id,result);return structuredClone(result);
 }
 confirm(draftId:string,revision:number,key:string):Receipt{
  const cache=draftId+':'+key,prior=this.confirmations.get(cache);if(prior)return {...prior,state:this.state()};
  this.connected();if(!key||key.length>128)throw Error('缺少有效確認識別碼');
  const draft=this.drafts.get(draftId);if(!draft||draft.status!=='REVIEW')throw Error('訂單已取消或確認');
  if(revision!==this.version||draft.revision!==this.version)throw Error('價格或帳戶已更新，請重新檢查訂單');
  const orderId=id();let status='FILLED';
  if(draft.order_type==='LIMIT'){
   this.pendingOrders.push({id:orderId,side:draft.side,lot:draft.lot,limit_price:draft.limit_price!,sl:draft.sl,tp:draft.tp,created_at:this.clock,action:draft.action,status:'PENDING'});
   status='PENDING';
  }else{
   const p:Position={id:orderId,side:draft.side,lot:draft.lot,entry:draft.price,sl:draft.sl,tp:draft.tp,opened_at:this.clock,pnl:'0.00'};
   this.positions.push(p);this.orders.push({id:p.id,position_id:p.id,side:p.side,lot:p.lot,price:p.entry,status:'FILLED',time:this.clock,action:draft.action});
  }
  draft.status=status;this.version++;const result={status,order_id:orderId,state:this.state()};this.confirmations.set(cache,result);return result;
 }
 cancel(draftId:string){const draft=this.drafts.get(draftId);if(!draft||draft.status!=='REVIEW')throw Error('草稿已失效');draft.status='CANCELLED';return {status:'CANCELLED'};}
 cancelPending(orderId:string){this.connected();const pending=this.pendingOrders.find(p=>p.id===orderId);if(!pending)throw Error('待成交限價單不存在或已觸價');this.pendingOrders=this.pendingOrders.filter(p=>p.id!==orderId);this.version++;return {status:'CANCELLED',order_id:orderId,state:this.state()};}
 private closeAt(p:Position,price:Decimal,reason="MANUAL"):Receipt{
  const pnl=price.minus(p.entry).times(p.lot).times(100).times(p.side==='BUY'?1:-1);this.balance=this.balance.plus(pnl);this.positions=this.positions.filter(x=>x.id!==p.id);
  const orderId=id();this.orders.push({id:orderId,position_id:p.id,reason,side:p.side==='BUY'?'SELL':'BUY',lot:p.lot,price:money(price),status:'FILLED',time:this.clock,action:'CLOSE',pnl:money(pnl)});this.version++;
  return {status:'FILLED',order_id:orderId,state:this.state()};
 }
 close(positionId:string,key:string):Receipt{
  const cache=positionId+':'+key,prior=this.closes.get(cache);if(prior)return {...prior,state:this.state()};
  this.connected();if(!key||key.length>128)throw Error('缺少有效確認識別碼');const p=this.positions.find(p=>p.id===positionId);if(!p)throw Error('部位已平倉或不存在');
  const result=this.closeAt(p,d(this.quote()[p.side==='BUY'?'bid':'ask']));this.closes.set(cache,result);return result;
 }
 step(count:number):State{
  this.connected();if(![1,6,12].includes(count))throw Error('只可推進1、6或12根');if(this.cursor+count>this.bars.length)throw Error('已到本次回放範圍末端');
  for(let i=0;i<count;i++){
   const bar=this.bars[this.cursor++];
   for(const p of [...this.positions]){
    const buy=p.side==='BUY',adjust=buy?d(0):d('.30'),lo=d(bar.low).plus(adjust),hi=d(bar.high).plus(adjust),opening=d(bar.open).plus(adjust),stop=p.sl?d(p.sl):null,target=p.tp?d(p.tp):null;
    if(stop&&(buy?lo.lte(stop):hi.gte(stop)))this.closeAt(p,buy?Decimal.min(stop,opening):Decimal.max(stop,opening),"STOP_LOSS_CONSERVATIVE");
    else if(target&&(buy?hi.gte(target):lo.lte(target)))this.closeAt(p,target,"TAKE_PROFIT");
   }
   for(const pending of [...this.pendingOrders]){
    const limit=d(pending.limit_price);
    const touched=pending.side==='BUY'?d(bar.low).plus('.30').lte(limit):d(bar.high).gte(limit);
    if(!touched)continue;
    this.pendingOrders=this.pendingOrders.filter(p=>p.id!==pending.id);
    const p:Position={id:pending.id,side:pending.side,lot:pending.lot,entry:pending.limit_price,sl:pending.sl,tp:pending.tp,opened_at:this.clock,pnl:'0.00'};
    const action=this.action(p.side);
    this.positions.push(p);this.orders.push({id:p.id,position_id:p.id,side:p.side,lot:p.lot,price:p.entry,status:'FILLED',time:this.clock,action});
   }
   this.version++;
  }return this.state();
 }
 caseDetail(caseId:string):Case{
  if(this.history){const item=this.history.detail(caseId,this.clock);if(!item)throw Error('案例不存在或尚不可用');return item;}
  const c=this.cases.find(c=>c.id===caseId&&c.available_at<=this.clock);if(!c)throw Error('案例不存在或尚不可用');
  return {...c,bars:[],markers:[],distance:null,match_reasons:[],differences:['合成流程案例，沒有真實歷史 K 線'],chart_reason:'此為合成流程案例；時區為示範設定，沒有真實案例行情可供驗證'};
 }
 audit():Audit{if(this.history)return this.history.audit();return {source_files:0,total_gold_records:this.cases.length,period:'合成示範案例；不是交易員統計',source:'synthetic_demo',refreshed_at:'2026-10-01',
  groups:Object.entries(labels).map(([code,label])=>({code,label,count:this.cases.filter(c=>c.behavior===code).length,description:'合成示範分類，用於展示介面'})),limitations:['GitHub Pages 不包含私人交易員紀錄','本機新版資料稽核的匿名彙總另見 GitHub docs/data-audit-summary.md']};}
 chat(message:string,side?:Side,typical_lot?:string|null){
  if(parseRuleMessage(message,[]))return {message:'這是設定、假設或取消語句；請在我的規則中設定，不會建立訂單。',draft:null,provider:'local_rules'};
  const requested=/賣|做空|\bSELL\b/i.test(message)?'SELL':/買|做多|\bBUY\b/i.test(message)?'BUY':message.includes('改')?side:null;
  const lot=message.match(/(\d+(?:\.\d+)?)\s*(?:手|lots?\b)/i);
  if(requested&&lot&&!/不要|別|不買|不賣|取消|不用/.test(message)){
   const draft=this.draft(requested,lot[1],message.match(/停損\s*([0-9]+(?:\.[0-9]+)?)/)?.[1],message.match(/停利\s*([0-9]+(?:\.[0-9]+)?)/)?.[1],typical_lot);
   return {message:'已準備'+draft.lot+'手草稿，尚未成交。這是本地規則解析，請核對案例與風險後自行確認。',draft,provider:'local_rules'};
  }
  const m=this.state().market;return {message:`本地助手：目前合成回放最近60根5分K變化 ${m.change_pct}%，區間 ${m.low} 至 ${m.high}；這是數值描述，不是買賣建議。可以輸入「買進黃金0.1手」準備待確認草稿。`,draft:null,provider:'local_rules'};
 }
}

const session=new DemoEngine();
export async function browserAPI(path:string,body?:unknown):Promise<unknown>{
 const [route,query]=path.split('?'),input=(body||{}) as Record<string,unknown>,params=new URLSearchParams(query);
 // Keep the workbench responsive while the public real-case archive loads.
 // Node tests exercise the synthetic engine without a browser or static archive.
 if(typeof document!=='undefined'&&(
   route==='/audit'||route==='/cases'||route.startsWith('/cases/')||
   route==='/drafts'||route==='/chat'
 ))session.history=await loadPublicHistory();
 const validatedRules=(route==='/drafts'||route==='/chat')?validateRules(input.personal_rules||[]):[];
 let result:unknown;
 if(route==='/state')result=session.state();
 else if(route==='/audit')result=session.audit();
 else if(route==='/bars')result=session.chart((params.get('interval')||'5m') as '5m'|'15m'|'1h',params.get('focus')||undefined);
 else if(route==='/cases')result=session.retrieve((params.get('side')||'BUY') as Side,(params.get('action')||'FIRST') as Action,params.get('lot')||'0.1',params.get('typical_lot'));
 else if(route.startsWith('/cases/'))result=session.caseDetail(decodeURIComponent(route.slice(7)));
 else if(route==='/replay/reset')result=session.reset();
 else if(route==='/replay/step')result=session.step(Number(input.bars));
 else if(route==='/mode'){if(input.mode!=='replay')throw Error('公開版沒有券商模擬帳戶；請使用合成回放');session.mode='replay';session.version++;result=session.state();}
 else if(route==='/drafts')result=session.draft(input.side as Side,String(input.lot),input.sl as string|null,input.tp as string|null,input.typical_lot as string|null,(input.order_type||'MARKET') as OrderType,input.limit_price as string|null);
 else if(/^\/drafts\/[^/]+\/confirm$/.test(route)){
  const saved=session.drafts.get(route.split('/')[2]) as (Draft & {rule_snapshot?:PersonalRule[]})|undefined;
  const rules=validateRules(input.personal_rules||[]);
  if(saved?.status==='REVIEW'&&JSON.stringify(saved.rule_snapshot||[])!==JSON.stringify(rules))throw Error('個人規則已更新，請重新檢查訂單');
  result=session.confirm(route.split('/')[2],Number(input.revision),String(input.idempotency_key||''));
 }
 else if(/^\/drafts\/[^/]+\/cancel$/.test(route))result=session.cancel(route.split('/')[2]);
 else if(/^\/pending\/[^/]+\/cancel$/.test(route))result=session.cancelPending(route.split('/')[2]);
 else if(/^\/positions\/[^/]+\/close$/.test(route)){if(input.confirmed!==true)throw Error('需要使用者確認平倉');result=session.close(route.split('/')[2],String(input.idempotency_key||''));}
 else if(route==='/chat')result=session.chat(String(input.message||''),input.side as Side,input.typical_lot as string|null);
 else throw Error('公開示範不支援此操作');
 if(route==='/drafts'||route==='/chat'){
   const rules=validatedRules,value=result as {draft?:Draft|null;personal_rules?:ReturnType<typeof evaluateRules>};
   const draft=route==='/drafts'?result as Draft:value.draft||null;
   const check=evaluateRules(rules,session.state(),draft,session.chart('5m').analysis?.reading);
   value.personal_rules=check;if(draft){draft.personal_rules=check;(session.drafts.get(draft.id)! as Draft & {rule_snapshot?:PersonalRule[]}).rule_snapshot=rules;}
 }
 return structuredClone(result);
}
