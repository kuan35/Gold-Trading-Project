import {useEffect,useState} from 'react';
import type {DraftInputState} from './conversationState';import type {DemoMarket} from './demoMarket';
import type {RiskSummary} from './TicketRiskPanel';
export type LevelPreview={status:string;reason:string|null;pnl_usd:string|null;price_return_pct:string|null;margin_roi_pct?:string|null};
type MarginPreview={source:'BROKER_EXPECTED'|'LEVERAGE_ESTIMATE'|'UNAVAILABLE';amount_usd:string|null;leverage:string|null;reason:string};
type Preview={status:string;reason:string|null;entry_price:string|null;quantity_oz:string|null;sl:LevelPreview|null;tp:LevelPreview|null;margin?:MarginPreview|null;risk?:RiskSummary;basis:string;quote_time_utc:string|null;conditional_on_fill?:boolean};
export type PreviewState={data:Preview|null;pending:boolean;error:string};
export function useTicketPreview(value:DraftInputState,market:DemoMarket|null):PreviewState{
 const input=JSON.stringify(value),hasLevel=Boolean(value.sl||value.tp),quote=market?.quote.source_time_utc??'',status=market?.quote.status??'';
 const [state,setState]=useState<{input:string;data:Preview|null;error:string}>({input:'',data:null,error:''}),[pending,setPending]=useState(false);
 useEffect(()=>{
  if(!hasLevel||status!=='CURRENT'||import.meta.env.MODE==='pages'){setPending(false);return;}
  let active=true;const controller=new AbortController();setPending(true);
  const timer=setTimeout(()=>void fetch('/api/broker/ticket-preview',{method:'POST',headers:{'Content-Type':'application/json'},body:input,signal:controller.signal}).then(async r=>{if(!r.ok)throw Error();return await r.json() as Preview;}).then(data=>{if(active)setState({input,data,error:''});}).catch(()=>{if(active)setState({input,data:null,error:'試算暫不可用，請確認本機服務。'});}).finally(()=>{if(active)setPending(false);}),120);
  return()=>{active=false;clearTimeout(timer);controller.abort();};
 },[input,hasLevel,quote,status]);
 return {data:hasLevel&&status==='CURRENT'&&state.input===input&&!state.error?state.data:null,pending:hasLevel&&status==='CURRENT'&&pending,error:hasLevel?(status!=='CURRENT'?'報價未就緒或已過期，暫不試算。':state.input===input?state.error:''):''};
}
export function TicketLevel({level}:{level:LevelPreview|null|undefined}){
 if(!level||level.status==='UNSET')return null;
 if(level.status!=='AVAILABLE')return <small className="ticket-preview-warning">{level.reason}</small>;
 const profit=level.pnl_usd?.startsWith('-')===false;
 return <output className={'ticket-level '+(profit?'positive':'negative')}><strong>{profit?'+':''}{level.pnl_usd} USD</strong><span>價格報酬率 {profit?'+':''}{level.price_return_pct}%</span>{level.margin_roi_pct!=null&&<span>預估保證金ROI {profit?'+':''}{level.margin_roi_pct}%</span>}</output>;
}
export function TicketPreviewNote({preview:p}:{preview:PreviewState}){
 if(!p.data)return p.pending?<small className="ticket-preview-note">更新試算中…</small>:p.error?<small className="ticket-preview-warning">{p.error}</small>:null;
 if(p.data.status!=='AVAILABLE')return <small className="ticket-preview-warning">{p.data.reason}</small>;
 const margin=p.data.margin;
 return <div className="ticket-preview-note">{margin?.amount_usd&&<p>預估保證金 <strong>{margin.amount_usd} USD</strong> · {margin.source==='BROKER_EXPECTED'?'券商預估':`1:${margin.leverage} 試算`}</p>}<details><summary>{p.pending?'更新試算中 · ':''}計算依據 · 進場 {p.data.entry_price}</summary><p>{p.data.quantity_oz} 盎司；{p.data.basis}</p>{margin&&<p>{margin.reason}</p>}{p.data.conditional_on_fill&&<p>限價單假設已成交，不代表一定觸價成交。</p>}<p>市價單採做多Ask／做空Bid，實際成交可能不同。</p></details></div>;
}
