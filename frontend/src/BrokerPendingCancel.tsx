import {useEffect,useRef,useState} from 'react';
import {api,key} from './api';
import type {DemoMarket} from './demoMarket';
import {CloseConfirmError,confirmBrokerClose} from './BrokerClosePanel';
type CancelDraft={id:string;revision:number;order_id:string;side:string;lot:string;limit_price:string|null;stop_price?:string|null;pending_intent?:string;explanation:string;expires_at_utc:string};
type Receipt={status:string;order_id?:string|null;status_observed_at_utc?:string};
export function pendingCancelReady(market:DemoMarket|null,orderId:string){
 const order=market?.account?.pending_orders.find(o=>o.id===orderId);
 return Boolean((market?.environment==='demo'||market?.environment==='live')&&market.connection_status==='CONNECTED'&&market.order_connection&&market.token_scope==='TRADE'&&market.account?.status==='CURRENT'&&market.quote.status==='CURRENT'&&market.quote.age_seconds!=null&&market.quote.age_seconds>=0&&market.quote.age_seconds<=5&&order&&['OPEN','CLOSE'].includes(order.intent??'')&&['LIMIT','STOP','STOP_LIMIT'].includes(order.order_type??''));
}
export default function BrokerPendingCancel({market,orderId}:{market:DemoMarket|null;orderId:string}){
 const [open,setOpen]=useState(false),[draft,setDraft]=useState<CancelDraft|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState(''),[result,setResult]=useState<Receipt|null>(null);
 const dialog=useRef<HTMLDialogElement>(null),working=useRef(false),confirmKey=useRef('');
 const environment=market?.environment??'demo',brokerPath=environment==='live'?'/live':'/broker';
 const ready=pendingCancelReady(market,orderId),unresolved=Boolean(result&&!['CANCELLED','REJECTED'].includes(result.status));
 // The order stays disabled until account polling actually removes it.
 const locked=unresolved||result?.status==='CANCELLED';
 useEffect(()=>{if(open)dialog.current?.showModal();else dialog.current?.close();},[open]);
 useEffect(()=>{if(!draft||!unresolved)return;let active=true;
  const timer=window.setInterval(()=>{void api<Receipt>(`${brokerPath}/drafts/${draft.id}/status`).then(value=>{if(active)setResult(value);}).catch(()=>{});},2500);
  return()=>{active=false;window.clearInterval(timer);};
 },[draft?.id,unresolved]);
 const review=async()=>{if(working.current||locked||!ready)return;working.current=true;setBusy(true);setError('');
  try{const value=await api<CancelDraft>(`${brokerPath}/pending/${encodeURIComponent(orderId)}/cancel-draft`,{});setDraft(value);confirmKey.current=key();}
  catch(e){setError(e instanceof Error?e.message:'無法核對掛單，請稍後再試。');}
  finally{working.current=false;setBusy(false);}
 };
 const close=async()=>{if(working.current)return;working.current=true;setBusy(true);
  try{if(draft&&!result){await api(`${brokerPath}/drafts/${draft.id}/cancel`,{});setDraft(null);}setOpen(false);}
  catch(e){setError(e instanceof Error?e.message:'無法關閉確認草稿，請稍後再試。');}
  finally{working.current=false;setBusy(false);}
 };
 const confirm=async()=>{if(working.current||locked||!ready||!draft)return;
  if(Date.now()>=Date.parse(draft.expires_at_utc)){await review();setError('已重新核對掛單，請確認取消。');return;}
  working.current=true;setBusy(true);setError('');setResult({status:'UNKNOWN'});
  try{setResult(await confirmBrokerClose(draft.id,draft.revision,confirmKey.current,environment));setOpen(false);}
  catch(e){if(e instanceof CloseConfirmError&&e.safeRejected)setResult({status:'REJECTED'});setError(e instanceof Error?e.message.replaceAll('平倉','取消掛單'):'回報未明，正在核對，請勿重送。');}
  finally{working.current=false;setBusy(false);}
 };
 return <span className="broker-pending-cancel"><button type="button" disabled={!ready||busy||locked} onClick={()=>{setDraft(null);setResult(null);setError('');setOpen(true);void review();}}>取消掛單</button>
  {result&&<small role="status">{result.status==='CANCELLED'?'券商已取消，正在更新待成交清單':result.status==='REJECTED'?'未能取消，請查看最新帳戶': '取消結果待核對，請勿重送'}</small>}
  <dialog ref={dialog} className="review-dialog" aria-label="取消待成交委託" onCancel={e=>{e.preventDefault();void close();}}><div className="dialog-heading"><h2>取消待成交委託</h2></div>
   <div className="dialog-body"><p>訂單 {orderId}</p>{busy&&!draft&&<p role="status">正在核對券商掛單…</p>}
    {draft&&<><p>{draft.pending_intent==='CLOSE'?'平倉掛單 · ':''}{draft.side==='BUY'?'買進':'賣出'} {draft.lot} 手{draft.limit_price?` · 指定價 ${draft.limit_price}`:''}{draft.stop_price?` · 觸發價 ${draft.stop_price}`:''}</p><p>{draft.explanation}</p></>}
    {error&&<p role="alert">{error}</p>}{unresolved&&<p role="status">取消結果待核對，請勿重送。</p>}
   </div><div className="dialog-actions"><button type="button" disabled={busy} onClick={()=>void close()}>關閉</button>{draft&&<button type="button" className="primary" disabled={busy||locked||!ready||result!==null} onClick={()=>void confirm()}>確認取消掛單</button>}{!draft&&!busy&&error&&<button type="button" disabled={!ready} onClick={()=>void review()}>重新核對</button>}</div>
  </dialog>
 </span>;
}
