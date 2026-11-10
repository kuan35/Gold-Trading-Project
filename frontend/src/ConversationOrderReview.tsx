import {AccountZeroEstimate} from './AccountScenario';
import {agentSummarySections,matchingAssessment,summaryEvidenceNote,type DraftAssessment} from './agentSummary';
import {AnswerSection} from './ConversationReply';
import {useEffect,useRef,useState} from 'react';
import {api,key} from './api';import type {Draft} from './types';import type {MarketReply} from './LiveAssistant';import {CloseConfirmError,confirmBrokerClose} from './BrokerClosePanel';import {submissionLocked} from './conversationState';
export type CheckedOrder=Draft&{expires_at_utc:string;analysis_reply:MarketReply;analysis_snapshot_id:string;analysis_as_of_utc:string;plan_id?:string;plan_record_error?:string};
type Result={status:string;execution_price?:string|null;order_id?:string|null;status_observed_at_utc?:string;error_code?:string|null;message?:string};
const label=(s:string)=>({UNKNOWN:'券商回報待核對，請勿重送',ACCEPTED:'券商已接受委託，等待成交或觸價',PARTIALLY_FILLED:'部分成交，等待券商後續回報',FILLED:'券商已回報成交',REJECTED:'委託未通過或遭券商拒絕',CANCELLED:'券商已取消',EXPIRED:'委託已過期'}[s]??'券商狀態待核對，請勿重送');
export default function ConversationOrderReview({draft,previousDraft,assessment,checkedRevision,currentRevision,accountUpdated,accountLast4,accountCurrency,externalBusy=false,onRefresh,onCancelled,onClear,onLock,onHistory,environment='demo'}:{draft:CheckedOrder;previousDraft?:CheckedOrder;assessment?:DraftAssessment;checkedRevision:number;currentRevision:number;accountUpdated?:string;accountLast4?:string|null;accountCurrency?:string|null;externalBusy?:boolean;onRefresh?:()=>Promise<void>;onCancelled?:()=>void;onClear:()=>void;onLock:(value:boolean)=>void;onHistory:()=>void;environment?:'demo'|'live'}){
 const brokerPath=environment==='live'?'/live':'/broker';
 const [result,setResult]=useState<Result|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState(''),[now,setNow]=useState(Date.now());
 const [needsRefresh,setNeedsRefresh]=useState(false);
 const working=useRef(false),confirmKey=useRef(key()),callback=useRef(onLock);callback.current=onLock;
 const locked=Boolean(result&&submissionLocked(result.status,result.status_observed_at_utc,accountUpdated));
 const expired=needsRefresh||!Number.isFinite(Date.parse(draft.expires_at_utc))||now>=Date.parse(draft.expires_at_utc);
 const agentReply=matchingAssessment(draft,assessment),summary=agentReply?agentSummarySections(agentReply):[];
 // Keep this submitted ticket immutable until the user explicitly starts a new
 // one. Only the receipt button uses the account-synchronization lock.
 useEffect(()=>{callback.current(busy||Boolean(result));},[busy,Boolean(result)]);
 useEffect(()=>{const t=window.setInterval(()=>setNow(Date.now()),1000);return()=>window.clearInterval(t);},[]);
 useEffect(()=>{if(!result||!submissionLocked(result.status)||['FILLED','REJECTED','CANCELLED','EXPIRED'].includes(result.status))return;
  let active=true;const t=window.setInterval(()=>{void api<Result>(`${brokerPath}/drafts/${draft.id}/status`).then(r=>{if(active)setResult(r);}).catch(()=>{});},2500);return()=>{active=false;window.clearInterval(t);};
 },[result?.status,draft.id,brokerPath]);
 const cancel=async()=>{if(working.current||locked||externalBusy)return;working.current=true;setBusy(true);onLock(true);try{if(!result){await api(`${brokerPath}/drafts/${draft.id}/cancel`,{});(onCancelled??onClear)();}else onClear();}catch(e){setError(String(e));}finally{working.current=false;setBusy(false);}};
 const refresh=async()=>{if(working.current||result||externalBusy||!onRefresh||currentRevision!==checkedRevision)return;
  working.current=true;setError('');try{await onRefresh();}catch(e){setError(e instanceof Error?e.message:'無法更新，請稍後再試。');}finally{working.current=false;}
 };
 const confirm=async()=>{if(working.current||externalBusy||result||expired||currentRevision!==checkedRevision||(environment==='live'&&(!accountLast4||accountCurrency!=='USD')))return;
  working.current=true;setBusy(true);onLock(true);setResult({status:'UNKNOWN'});setError('');
  try{const r=await confirmBrokerClose(draft.id,draft.revision,confirmKey.current,environment);setResult({...r,status_observed_at_utc:r.status_observed_at_utc??new Date().toISOString()});}
  catch(e){if(e instanceof CloseConfirmError&&e.safeRejected){
    if(/超過 30 秒|已過期|草稿已失效|報價變動|請重建草稿|帳戶或商品規格已變/.test(e.message)){setResult(null);setNeedsRefresh(true);}
    else setResult({status:'REJECTED'});
   }setError(e instanceof Error?e.message.replaceAll('平倉','委託'):'回報未知，請核對券商帳戶，勿重送。');}
  finally{working.current=false;setBusy(false);}
 };
 return <section className="cw-review" aria-label={`最新 ${environment.toUpperCase()} 委託核對`}><h3>{result?'委託回報':'確認前核對'}</h3>
  <p><strong>cTrader {environment.toUpperCase()}{environment==='live'?' · 真實資金':' · 模擬資金'}</strong> · 帳戶末四碼 {accountLast4??'未確認'} · {accountCurrency??'幣別未確認'}</p>
  {!result&&<section className="cw-review-assistant" aria-label="這筆委託的助手評估">{summary.length?<><small>助手評估 · 同一份委託快照</small>{summary.map((section,i)=><AnswerSection key={i} section={section}/>)}{agentReply&&summaryEvidenceNote(agentReply)&&<p role="status" className="fine">{summaryEvidenceNote(agentReply)}</p>}</>:<p role="status">{assessment?.state==='pending'?'助手正在評估這筆委託…':assessment?.state==='error'?`助手未完成解讀：${assessment.error??'請重新檢查助手連線。'}`:assessment?.state==='stale'||previousDraft?'報價與風險已更新；先前助手說明屬於舊快照。':'已完成欄位與風險檢查，尚無這份草稿的助手評估。'}</p>}</section>}
  {draft.plan_id&&<p className="fine">交易計畫已保存，可從上方「計畫」回顧當時依據。</p>}
  <p><strong>{draft.side==='BUY'?'做多':'做空'} {draft.lot} 手 · {draft.order_type==='LIMIT'?'限價':'市價'}</strong></p><p>參考價 {draft.price} · SL {draft.sl??'未設定'} · TP {draft.tp??'未設定'}</p>
  <p>總曝險手數 {draft.risk.before_lot} → {draft.risk.after_lot}</p><p>停損情境損失 {draft.risk.stop_loss_usd===null?'未設定':draft.risk.stop_loss_usd+' USD'}</p>
  {environment==='live'&&draft.risk.live&&<p>券商預估保證金 {draft.risk.live.broker_margin_usd} USD · 帳戶淨值 {draft.risk.live.equity_usd} USD · 黃金持倉與掛單合計 {draft.risk.live.gross_after_lot} 手</p>}
  <AccountZeroEstimate value={draft.risk.account_zero}/><details><summary>價格情境與提醒</summary>{draft.risk.scenarios.map((s,i)=><p key={i}>逆向 {s.move}：{s.loss} USD</p>)}{draft.risk.warnings.map((w,i)=><p key={i}>{w}</p>)}</details>
  {previousDraft&&!result&&<section aria-label="委託更新對照"><strong>報價與風險已更新，請核對後確認送出</strong><p>已保留填寫欄位；先前助手解讀仍屬原分析快照。</p><p>參考價 {previousDraft.price} → {draft.price}</p><p>下單後總手數 {previousDraft.risk.after_lot} → {draft.risk.after_lot}</p><p>停損情境損失 {previousDraft.risk.stop_loss_usd??'未設定'} → {draft.risk.stop_loss_usd??'未設定'} USD</p></section>}
  {!result&&<p className="fine">{expired?'欄位已保留，更新最新報價與風險後即可繼續。':'確認時會再次核對最新報價與帳戶。'}</p>}
  {result&&<p role="status"><strong>{label(result.status)}</strong>{result.execution_price&&` · 成交價 ${result.execution_price}`}</p>}{error&&<p role="alert">{error}</p>}
  {result&&locked&&<p className="fine">{['ACCEPTED','PARTIALLY_FILLED','FILLED'].includes(result.status)?'正在同步委託後的帳戶資料，同步完成即可準備下一筆。':'回報尚未確認，請先核對券商紀錄，暫不新增委託。'}</p>}
  {result&&!locked&&<p className="fine">可準備下一筆；原有持倉與掛單會保留，每筆仍須重新檢查與確認。</p>}
  <div className="cw-actions">{!result&&(expired&&onRefresh?<button type="button" className="primary" disabled={externalBusy||busy||currentRevision!==checkedRevision} onClick={()=>void refresh()}>{externalBusy?'更新報價中…':'更新報價並繼續'}</button>:<button type="button" className="primary" disabled={externalBusy||busy||expired||currentRevision!==checkedRevision||(environment==='live'&&(!accountLast4||accountCurrency!=='USD'))} onClick={()=>void confirm()}>確認送出 {environment.toUpperCase()} 委託</button>)}<button type="button" disabled={externalBusy||busy||locked} onClick={()=>void cancel()}>{result?'準備下一筆委託':'取消草稿'}</button>{result&&<button type="button" onClick={onHistory}>查看持倉與紀錄</button>}</div>
 </section>;
}
