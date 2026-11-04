import {useEffect,useRef,useState} from 'react';
import type {DraftInputState,InputPatch} from './conversationState';
import type {PreviewState} from './TicketPreview';
export type RiskSummary={status:string;reason:string|null;stop_loss_usd:string|null;stop_equity_pct:string|null;reward_risk_ratio:string|null;existing_positions_risk_usd:string|null;pending_orders_risk_usd:string|null;gold_total_risk_usd:string|null;gold_total_equity_pct:string|null;unprotected_positions:string[];unprotected_orders:string[];scope:string};
type Sizing={status:string;reason:string|null;lot:string|null;actual_risk_usd:string|null;budget_usd:string|null;stop_equity_pct:string|null};
export function RiskNumbers({risk:r}:{risk:RiskSummary}){
 return <section className="ticket-risk-summary" aria-label="帳戶與本筆風險"><dl><div><dt>本筆停損占淨值</dt><dd>{r.stop_equity_pct===null?'資料不足':r.stop_equity_pct+'%'}</dd></div><div><dt>風險：預期獲利</dt><dd>{r.reward_risk_ratio===null?'待填有效停損／停利':'1：'+r.reward_risk_ratio}</dd></div></dl><details><summary>黃金合計情境風險</summary><p>{r.gold_total_risk_usd===null?'無法完整估算':`${r.gold_total_risk_usd} USD${r.gold_total_equity_pct!==null?' · 淨值 '+r.gold_total_equity_pct+'%':''}`}</p>{r.reason&&<p>{r.reason}</p>}<p className="fine">{r.scope}</p><p className="fine">按各停損估計額外不利變動；未扣成本、未互抵多空，不保證損失上限。</p></details></section>;
}
export default function TicketRiskPanel({value,onPatch,preview,disabled=false,id}:{value:DraftInputState;onPatch:(p:InputPatch)=>void;preview:PreviewState;disabled?:boolean;id:string}){
 const [mode,setMode]=useState<'usd'|'pct'>('usd'),[budget,setBudget]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState(''),[sized,setSized]=useState<{input:string;result:Sizing}|null>(null);
 const request=useRef<AbortController|null>(null),current=useRef(value),generation=useRef(0);current.current=value;
 const input=JSON.stringify(value),usable=sized?.input===input?sized.result:null;
 useEffect(()=>()=>{generation.current++;request.current?.abort();},[]);
 useEffect(()=>{generation.current++;request.current?.abort();setBusy(false);setError('');},[input,mode,budget]);
 const calculate=async(apply=false)=>{
  if(disabled||!budget.trim()||!value.sl||busy)return;
  const token=++generation.current,source=JSON.stringify(current.current);request.current?.abort();const controller=new AbortController();request.current=controller;setBusy(true);setError('');
  try{
   const response=await fetch('/api/trading/risk-size',{method:'POST',headers:{'Content-Type':'application/json'},signal:controller.signal,body:JSON.stringify({draft:current.current,...(mode==='usd'?{risk_usd:budget}:{equity_pct:budget})})});
   const result=await response.json();if(!response.ok)throw Error(result.detail||'無法計算手數');
   if(token!==generation.current||JSON.stringify(current.current)!==source)return;
   setSized({input:source,result});
   if(apply&&result.status==='AVAILABLE'&&result.lot)onPatch({lot:result.lot});
  }catch(e){if(token===generation.current&&!controller.signal.aborted)setError(e instanceof Error?e.message:'手數試算暫不可用。');}
  finally{if(token===generation.current)setBusy(false);}
 };
 return <div className="ticket-risk-panel">{preview.data?.risk&&<RiskNumbers risk={preview.data.risk}/>}<details><summary>依可承擔風險反算手數</summary><label htmlFor={id+'-risk-mode'}>預算方式<select id={id+'-risk-mode'} disabled={disabled||busy} value={mode} onChange={e=>{setMode(e.target.value as 'usd'|'pct');setSized(null);}}><option value="usd">風險金額 USD</option><option value="pct">帳戶淨值比例 %</option></select></label><label htmlFor={id+'-risk-budget'}>{mode==='usd'?'最多承擔的名目損失 USD':'最多承擔的淨值比例 %'}<input id={id+'-risk-budget'} type="number" min="0" step="any" value={budget} disabled={disabled||busy} placeholder="自行設定風險預算" onChange={e=>{setBudget(e.target.value);setSized(null);}}/></label><button type="button" disabled={disabled||busy||!budget.trim()||!value.side||!value.order_type||!value.sl||(value.order_type==='LIMIT'&&!value.limit_price)||Boolean(preview.error)} onClick={()=>void calculate()}>{busy?'計算中…':'計算手數'}</button>{!value.sl&&<small>請先填有效停損價。</small>}{usable&&<div className="ticket-sizing-result" role="status">{usable.status==='AVAILABLE'?<><p>試算 {usable.lot} 手 · 停損約 {usable.actual_risk_usd} USD</p><button type="button" disabled={disabled||busy} onClick={()=>void calculate(true)}>以最新報價重算並套用手數</button></>:<p>{usable.reason}</p>}</div>}{error&&<p role="alert">{error}</p>}</details></div>;
}
