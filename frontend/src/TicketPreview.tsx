import {AccountZeroEstimate,type AccountZero} from './AccountScenario';
import {readAPIResponse} from './api';
import {useEffect,useState} from 'react';
import type {DraftInputState} from './conversationState';import type {DemoMarket} from './demoMarket';
import type {RiskSummary} from './TicketRiskPanel';
export type LevelPreview={status:string;reason:string|null;pnl_usd:string|null;price_return_pct:string|null;margin_roi_pct?:string|null};
type MarginPreview={source:'BROKER_EXPECTED'|'LEVERAGE_ESTIMATE'|'UNAVAILABLE';amount_usd:string|null;leverage:string|null;reason:string};
type Preview={status:string;reason:string|null;entry_price:string|null;quantity_oz:string|null;sl:LevelPreview|null;tp:LevelPreview|null;margin?:MarginPreview|null;risk?:RiskSummary;basis:string;quote_time_utc:string|null;conditional_on_fill?:boolean;account_zero?:AccountZero};
export type PreviewState={data:Preview|null;pending:boolean;error:string};
export function useTicketPreview(value:DraftInputState,market:DemoMarket|null):PreviewState{
 const input=JSON.stringify(value),canPreview=Boolean(value.side&&value.order_type&&value.lot&&(value.order_type!=='LIMIT'||value.limit_price)),status=market?.quote.status??'',environment=market?.environment??'demo';
 const [state,setState]=useState<{input:string;data:Preview|null;error:string}>({input:'',data:null,error:''}),[pending,setPending]=useState(false);
 useEffect(()=>{
  if(!canPreview||status!=='CURRENT'||import.meta.env.MODE==='pages'){setPending(false);return;}
  let active=true,timer:ReturnType<typeof setTimeout>;const controller=new AbortController();
  const refresh=async()=>{
   if(!active)return;setPending(true);
   try{
    const response=await fetch(`/api/${environment==='live'?'live':'broker'}/ticket-preview`,{method:'POST',headers:{'Content-Type':'application/json'},body:input,signal:controller.signal});
    const data=await readAPIResponse<Preview>(response);if(active)setState({input,data,error:''});
   }catch(e){if(active&&!controller.signal.aborted)setState(previous=>({input,data:previous.input===input?previous.data:null,error:e instanceof Error?e.message:'試算更新失敗，稍後重試。'}));}
   finally{if(active){setPending(false);timer=setTimeout(()=>void refresh(),1000);}}
  };
  // One non-overlapping refresh loop: every tick must not abort an in-flight
  // preview or tear down the rendered risk blocks.
  setPending(true);timer=setTimeout(()=>void refresh(),120);
  return()=>{active=false;clearTimeout(timer);controller.abort();};
 },[input,canPreview,status,environment]);
 return {data:canPreview&&status==='CURRENT'&&state.input===input?state.data:null,pending:canPreview&&status==='CURRENT'&&pending,error:canPreview?(status!=='CURRENT'?'報價未就緒或已過期，暫不試算。':state.input===input?state.error:''):''};
}
export function TicketLevel({level}:{level:LevelPreview|null|undefined}){
 if(!level||level.status==='UNSET')return null;
 if(level.status!=='AVAILABLE')return <small className="ticket-preview-warning">{level.reason}</small>;
 const profit=level.pnl_usd?.startsWith('-')===false;
 return <output className={'ticket-level '+(profit?'positive':'negative')}><strong>{profit?'+':''}{level.pnl_usd} USD</strong><span>價格報酬率 {profit?'+':''}{level.price_return_pct}%</span>{level.margin_roi_pct!=null&&<span>預估保證金報酬率 {profit?'+':''}{level.margin_roi_pct}%</span>}</output>;
}
export function TicketPreviewNote({preview:p}:{preview:PreviewState}){
 if(!p.data)return p.pending?<small className="ticket-preview-note">更新試算中…</small>:p.error?<small className="ticket-preview-warning">{p.error}</small>:null;
 if(p.data.status!=='AVAILABLE')return <small className="ticket-preview-warning">{p.data.reason}</small>;
 const margin=p.data.margin;
 return <div className="ticket-preview-note" aria-busy={p.pending}><span className="ticket-preview-update" role="status">{p.error?'上次試算 · 更新暫未完成':p.pending?'上次試算 · 更新中':'試算已更新'}</span>{margin?.amount_usd&&<p>預估保證金 <strong>{margin.amount_usd} USD</strong> · {margin.source==='BROKER_EXPECTED'?'券商預估':`1:${margin.leverage} 試算`}</p>}<AccountZeroEstimate value={p.data.account_zero} pending={p.pending}/><details><summary>計算依據 · 進場 {p.data.entry_price}</summary><p>{p.data.quantity_oz} 盎司；{p.data.basis}</p>{margin&&<p>{margin.reason}</p>}{p.data.conditional_on_fill&&<p>限價單假設已成交，不代表一定觸價成交。</p>}<p>市價做多採目前可買進價、做空採目前可賣出價；實際成交可能不同。</p>{p.error&&<p>{p.error}</p>}</details></div>;
}
