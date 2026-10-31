import {useEffect,useId,useRef,useState} from 'react';
import Decimal from 'decimal.js';
import {api,key} from './api';
import type {DemoMarket} from './demoMarket';

type CloseDraft={id:string;revision:number;status:string;intent:'CLOSE';position_id:string;
  side:'BUY'|'SELL';lot:string;price:string;order_type?:string;limit_price?:string|null;expires_at_utc:string;explanation:string};
type CloseResult={status:string;client_order_id?:string;position_id?:string;order_id?:string|null;
  execution_price?:string|null;message?:string;error_code?:string|null;status_observed_at_utc?:string;local_rejection?:boolean};
const pending=(status:string)=>['UNKNOWN','ACCEPTED','PARTIALLY_FILLED'].includes(status);
export class CloseConfirmError extends Error{
  constructor(message:string,public readonly safeRejected:boolean){super(message);this.name='CloseConfirmError';}
}
export async function confirmBrokerClose(id:string,revision:number,idempotencyKey:string):Promise<CloseResult>{
  // Preserve explicit server rejection status; api() exposes only a plain Error.
  const response=await fetch(`/api/broker/drafts/${encodeURIComponent(id)}/confirm`,{
    method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({revision,idempotency_key:idempotencyKey})});
  const content:unknown=await response.json().catch(()=>null);
  if(!response.ok){
    const detail=content&&typeof content==='object'&&'detail' in content&&typeof content.detail==='string'?content.detail:null;
    const explicit=[400,401,403,404,405,409,410,415,422,429].includes(response.status)&&Boolean(detail)&&
      Boolean(response.headers.get('content-type')?.includes('application/json'));
    throw new CloseConfirmError(detail??'無法確認券商是否收到平倉；請核對帳戶，勿重送。',explicit);
  }
  if(!content||typeof content!=='object'||!('status' in content)||typeof content.status!=='string')
    throw new CloseConfirmError('平倉回報格式無效；請核對帳戶，勿重送。',false);
  return content as CloseResult;
}
export function brokerCloseLocked(status:string,observed?:string,accountUpdated?:string):boolean{
  if(pending(status))return true;
  if(status!=='FILLED')return false;
  const last=Date.parse(observed??''),account=Date.parse(accountUpdated??'');
  return !Number.isFinite(last)||!Number.isFinite(account)||account<=last;
}
const resultLabel=(status:string)=>({ACCEPTED:'券商已接受平倉，等待成交回報',FILLED:'券商已回報平倉成交',
  PARTIALLY_FILLED:'券商回報部分平倉，等待剩餘回報',REJECTED:'券商拒絕平倉',CANCELLED:'券商已取消平倉',
  EXPIRED:'平倉委託已過期',UNKNOWN:'平倉回報待核對，請至 cTrader 帳戶確認，勿重送'}[status]??`券商狀態：${status}`);

export function brokerCloseReady(market:DemoMarket|null,positionId:string):boolean{
  if(!market||market.environment!=='demo'||!market.order_connection||market.token_scope!=='TRADE'||!market.symbol||
    market.quote.status!=='CURRENT'||market.account?.status!=='CURRENT'||market.quote.age_seconds===null||
    market.quote.age_seconds===undefined||!Number.isFinite(market.quote.age_seconds)||market.quote.age_seconds>5||market.quote.age_seconds<0)return false;
  const position=market.account.positions.find(item=>item.id===positionId);
  if(!position)return false;
  try{
    const volume=new Decimal(position.volume_units).times(100);
    const bid=new Decimal(market.quote.bid??''),ask=new Decimal(market.quote.ask??'');
    return volume.isFinite()&&volume.gt(0)&&volume.isInteger()&&bid.isFinite()&&bid.gt(0)&&ask.isFinite()&&ask.gte(bid);
  }catch{return false;}
}

export default function BrokerClosePanel({market,positionId,onUpdated}:{market:DemoMarket|null;positionId:string;onUpdated?:()=>void}){
  const [draft,setDraft]=useState<CloseDraft|null>(null);
  const [submission,setSubmission]=useState<{draftId:string;result:CloseResult}|null>(null);
  const [busy,setBusy]=useState(false),[error,setError]=useState('');
  const [limit,setLimit]=useState('');
  const dialog=useRef<HTMLDialogElement>(null),working=useRef(false),confirmKey=useRef('');
  const updated=useRef(onUpdated),heading=useId();
  const ready=brokerCloseReady(market,positionId);
  const locked=Boolean(submission&&brokerCloseLocked(submission.result.status,submission.result.status_observed_at_utc,market?.account?.updated_at_utc));
  useEffect(()=>{updated.current=onUpdated;},[onUpdated]);
  useEffect(()=>{
    if(draft&&!dialog.current?.open)dialog.current?.showModal();
    if(!draft&&dialog.current?.open)dialog.current.close();
  },[draft]);
  useEffect(()=>{
    if(!submission||!pending(submission.result.status))return;
    let active=true;let timer:number|undefined;
    const refresh=async()=>{
      try{
        const result=await api<CloseResult>(`/broker/drafts/${submission.draftId}/status`);
        if(!active)return;
        setSubmission({draftId:submission.draftId,result});updated.current?.();
        if(!pending(result.status))return;
      }catch{/* A failed status read never sends another close command. */}
      if(active)timer=window.setTimeout(refresh,2500);
    };
    timer=window.setTimeout(refresh,2500);
    return()=>{active=false;if(timer)window.clearTimeout(timer);};
  },[submission?.draftId,submission?.result.status]);
  const review=async(orderType:'MARKET'|'LIMIT'='MARKET')=>{
    if(working.current||locked||!ready)return;
    working.current=true;setBusy(true);setError('');
    try{
      const next=await api<CloseDraft>(`/broker/positions/${encodeURIComponent(positionId)}/close-draft`,{order_type:orderType,limit_price:orderType==='LIMIT'?limit:null});
      confirmKey.current=key();setDraft(next);setSubmission(null);
    }catch(e){setError(e instanceof Error?e.message:'無法建立 DEMO 平倉草稿');}
    finally{working.current=false;setBusy(false);}
  };
  const cancel=async()=>{
    if(!draft||working.current)return;
    working.current=true;setBusy(true);setError('');
    try{await api(`/broker/drafts/${draft.id}/cancel`,{});setDraft(null);}
    catch(e){setError(e instanceof Error?e.message:'無法取消平倉草稿');}
    finally{working.current=false;setBusy(false);}
  };
  const confirm=async()=>{
    if(!draft||working.current||locked)return;
    working.current=true;setBusy(true);setError('');
    const draftId=draft.id;
    // Lock immediately: even a lost HTTP response may follow a broker submission.
    setSubmission({draftId,result:{status:'UNKNOWN'}});
    try{
      const result=await confirmBrokerClose(draftId,draft.revision,confirmKey.current);
      setSubmission({draftId,result});
    }catch(e){
      if(e instanceof CloseConfirmError&&e.safeRejected)setSubmission({draftId,result:{status:'REJECTED',local_rejection:true}});
      setError(e instanceof Error?e.message:'無法確認券商是否收到平倉；請核對帳戶，勿重送。');
    }finally{
      setDraft(null);working.current=false;setBusy(false);updated.current?.();
    }
  };
  return <span className="broker-close-control" aria-label={`cTrader DEMO 部位 ${positionId} 平倉`}>
    <button type="button" disabled={busy||!ready||locked} onClick={()=>void review()} title="cTrader DEMO：平倉此部位全部剩餘數量">平倉</button>
    <details><summary>限價平倉</summary><label>指定平倉價<input type="text" inputMode="decimal" value={limit} onChange={e=>setLimit(e.target.value)}/></label><button disabled={busy||!ready||locked||!limit} onClick={()=>void review('LIMIT')}>檢查限價平倉</button></details>
    {submission&&<span role="status" className="fine">{submission.result.local_rejection?'平倉確認未通過，請重新檢查草稿':resultLabel(submission.result.status)}
      {submission.result.execution_price?` · 成交價 ${submission.result.execution_price}`:''}
      {submission.result.error_code?` · ${submission.result.error_code}`:''}</span>}
    {error&&<span className="modal-error" role="alert">{error}</span>}
    <dialog ref={dialog} className="review-dialog" aria-labelledby={heading} onCancel={event=>{event.preventDefault();void cancel();}}>
      {draft&&<><div className="dialog-heading"><h2 id={heading}>核對 cTrader DEMO 平倉</h2>
        <button type="button" disabled={busy} aria-label="關閉 DEMO 平倉草稿" onClick={()=>void cancel()}>×</button></div>
        <div className="dialog-body"><p>部位 {draft.position_id} · 原方向 {draft.side} · 全部剩餘 {draft.lot} 手</p>
          <p>{draft.order_type==='LIMIT'?`掛單指定價 ${draft.limit_price}，等待原部位平倉`:`市價平倉參考價 ${draft.price}（${draft.side==='BUY'?'BID':'ASK'}）`}</p><p>{draft.explanation}</p>
          <p className="fine">草稿有效 30 秒。確認時重新核對帳戶與剩餘數量，實際成交以券商回報為準。</p>
          {error&&<p className="modal-error" role="alert">{error}</p>}</div>
        <div className="dialog-actions"><button type="button" disabled={busy} onClick={()=>void cancel()}>取消草稿</button>
          <button type="button" className="primary" disabled={busy||!ready||locked} onClick={()=>void confirm()}>{busy?'等待券商回報…':'確認平倉 DEMO 部位'}</button></div></>}
    </dialog>
  </span>;
}
