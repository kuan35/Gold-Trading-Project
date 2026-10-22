import {useEffect,useRef,useState} from 'react';
import {api,key} from './api';import type {Draft} from './types';import type {MarketReply} from './LiveAssistant';import {CloseConfirmError,confirmBrokerClose} from './BrokerClosePanel';import {submissionLocked} from './conversationState';
export type CheckedOrder=Draft&{expires_at_utc:string;analysis_reply:MarketReply;analysis_snapshot_id:string;analysis_as_of_utc:string};
type Result={status:string;execution_price?:string|null;order_id?:string|null;status_observed_at_utc?:string;error_code?:string|null;message?:string};
const label=(s:string)=>({UNKNOWN:'券商回報待核對，請勿重送',ACCEPTED:'券商已接受委託，等待成交或觸價',PARTIALLY_FILLED:'部分成交，等待券商後續回報',FILLED:'券商已回報成交',REJECTED:'委託未通過或遭券商拒絕',CANCELLED:'券商已取消',EXPIRED:'委託已過期'}[s]??'券商狀態待核對，請勿重送');
export default function ConversationOrderReview({draft,checkedRevision,currentRevision,accountUpdated,onClear,onLock,onHistory}:{draft:CheckedOrder;checkedRevision:number;currentRevision:number;accountUpdated?:string;onClear:()=>void;onLock:(value:boolean)=>void;onHistory:()=>void}){
 const [result,setResult]=useState<Result|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState(''),[now,setNow]=useState(Date.now());
 const working=useRef(false),confirmKey=useRef(key()),callback=useRef(onLock);callback.current=onLock;
 const locked=Boolean(result&&submissionLocked(result.status,result.status_observed_at_utc,accountUpdated));
 const expired=!Number.isFinite(Date.parse(draft.expires_at_utc))||now>=Date.parse(draft.expires_at_utc);
 useEffect(()=>{callback.current(busy||locked);},[busy,locked]);
 useEffect(()=>{const t=window.setInterval(()=>setNow(Date.now()),1000);return()=>window.clearInterval(t);},[]);
 useEffect(()=>{if(!result||!submissionLocked(result.status)||['FILLED','REJECTED','CANCELLED','EXPIRED'].includes(result.status))return;
  let active=true;const t=window.setInterval(()=>{void api<Result>(`/broker/drafts/${draft.id}/status`).then(r=>{if(active)setResult(r);}).catch(()=>{});},2500);return()=>{active=false;window.clearInterval(t);};
 },[result?.status,draft.id]);
 const cancel=async()=>{if(working.current||locked)return;working.current=true;setBusy(true);try{if(!result)await api(`/broker/drafts/${draft.id}/cancel`,{});onClear();}catch(e){setError(String(e));}finally{working.current=false;setBusy(false);}};
 const confirm=async()=>{if(working.current||result||expired||currentRevision!==checkedRevision)return;
  working.current=true;setBusy(true);onLock(true);setResult({status:'UNKNOWN'});setError('');
  try{const r=await confirmBrokerClose(draft.id,draft.revision,confirmKey.current);setResult({...r,status_observed_at_utc:r.status_observed_at_utc??new Date().toISOString()});}
  catch(e){if(e instanceof CloseConfirmError&&e.safeRejected)setResult({status:'REJECTED'});setError(e instanceof Error?e.message.replaceAll('平倉','委託'):'回報未知，請核對券商帳戶，勿重送。');}
  finally{working.current=false;setBusy(false);}
 };
 return <section className="cw-review" aria-label="最新 DEMO 委託核對"><h3>{result?'委託回報':'確認前核對'}</h3>
  <p><strong>{draft.side==='BUY'?'做多':'做空'} {draft.lot} 手 · {draft.order_type==='LIMIT'?'限價':'市價'}</strong></p><p>參考價 {draft.price} · SL {draft.sl??'未設定'} · TP {draft.tp??'未設定'}</p>
  <p>總曝險手數 {draft.risk.before_lot} → {draft.risk.after_lot}</p><p>停損情境損失 {draft.risk.stop_loss_usd===null?'未設定':draft.risk.stop_loss_usd+' USD'}</p>
  <details><summary>價格情境與提醒</summary>{draft.risk.scenarios.map((s,i)=><p key={i}>逆向 {s.move}：{s.loss} USD</p>)}{draft.risk.warnings.map((w,i)=><p key={i}>{w}</p>)}</details>
  {!result&&<p className="fine">{expired?'草稿已過期，請重新檢查':`有效至 ${new Date(draft.expires_at_utc).toLocaleTimeString('zh-TW',{hour12:false})}，確認時後端再次核對。`}</p>}
  {result&&<p role="status"><strong>{label(result.status)}</strong>{result.execution_price&&` · 成交價 ${result.execution_price}`}</p>}{error&&<p role="alert">{error}</p>}
  <div className="cw-actions">{!result&&<button type="button" className="primary" disabled={busy||expired||currentRevision!==checkedRevision} onClick={()=>void confirm()}>確認送出 DEMO 委託</button>}<button type="button" disabled={busy||locked} onClick={()=>void cancel()}>{result?'完成':'取消草稿'}</button>{result&&<button type="button" onClick={onHistory}>查看持倉與紀錄</button>}</div>
 </section>;
}
