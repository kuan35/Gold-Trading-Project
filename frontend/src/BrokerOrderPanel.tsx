import {useEffect,useRef,useState,type FormEvent} from 'react';
import {api,key} from './api';
import type {DemoMarket} from './demoMarket';
import type {Draft,OrderType,Side,LiveRetrievalMethod} from './types';
import {PoolEvidence} from './SimilarityEvidence';
import DraftCaseAssistant from './DraftCaseAssistant';

type BrokerResult={client_order_id:string;status:string;order_id?:string|null;position_id?:string|null;execution_price?:string|null;error_code?:string|null;message?:string};

const resultLabel=(status:string)=>({ACCEPTED:'券商已接受，等待成交或觸價',FILLED:'券商已回報成交',
  PARTIALLY_FILLED:'券商回報部分成交',REJECTED:'券商拒單',UNKNOWN:'回報狀態未知，請至 cTrader 帳戶核對，勿重送',
  CANCELLED:'券商已取消',EXPIRED:'券商委託已過期'}[status]??`券商狀態：${status}`);

export default function BrokerOrderPanel({market,side,onSideChange,retrievalMethod}:{market:DemoMarket|null;side:Side;onSideChange:(side:Side)=>void;retrievalMethod:LiveRetrievalMethod}){
  const [lot,setLot]=useState('0.10'),[orderType,setOrderType]=useState<OrderType>('MARKET');
  const [limit,setLimit]=useState(''),[sl,setSl]=useState(''),[tp,setTp]=useState('');
  const [draft,setDraft]=useState<Draft|null>(null),[result,setResult]=useState<BrokerResult|null>(null);
  const [busy,setBusy]=useState(false),[error,setError]=useState('');
  const dialog=useRef<HTMLDialogElement>(null),confirmKey=useRef('');
  const tradeReady=Boolean(market?.order_connection&&market.quote.age_seconds!==null&&
    market.quote.age_seconds!==undefined&&market.quote.age_seconds<=5);
  useEffect(()=>{if(draft&&!dialog.current?.open)dialog.current?.showModal();if(!draft&&dialog.current?.open)dialog.current.close();},[draft]);
  useEffect(()=>{if(!result?.client_order_id||!draft||!['ACCEPTED','PARTIALLY_FILLED','UNKNOWN'].includes(result.status))return;
    let active=true;
    const timer=window.setInterval(()=>{void api<BrokerResult>(`/broker/drafts/${draft.id}/status`).then(next=>{if(active)setResult(next);}).catch(()=>{});},2500);
    return()=>{active=false;window.clearInterval(timer);};
  },[result?.status,result?.client_order_id,draft?.id]);
  const review=async(event:FormEvent)=>{event.preventDefault();if(busy)return;setBusy(true);setError('');setResult(null);
    try{const next=await api<Draft>('/broker/drafts',{side,lot,order_type:orderType,retrieval_method:retrievalMethod,
      limit_price:orderType==='LIMIT'?limit:null,sl:sl.trim()||null,tp:tp.trim()||null});
      confirmKey.current=key();setDraft(next);
    }catch(e){setError(e instanceof Error?e.message:'無法建立 DEMO 草稿');}finally{setBusy(false);}
  };
  const cancel=async()=>{if(!draft||busy)return;setBusy(true);setError('');
    try{if(!result)await api(`/broker/drafts/${draft.id}/cancel`,{});setDraft(null);setResult(null);}
    catch(e){setError(e instanceof Error?e.message:'無法取消草稿');}finally{setBusy(false);}
  };
  const confirm=async()=>{if(!draft||busy||result)return;setBusy(true);setError('');
    try{setResult(await api<BrokerResult>(`/broker/drafts/${draft.id}/confirm`,
      {revision:draft.revision,idempotency_key:confirmKey.current}));}
    catch(e){setError(e instanceof Error?e.message:'DEMO 確認失敗');}finally{setBusy(false);}
  };
  return <section className="broker-order-panel" aria-label="cTrader DEMO 委託"><h3>DEMO 委託</h3>
    <p className="fine">僅本機 cTrader DEMO 帳戶。草稿建立時不送單；你在確認視窗按下確認後才送給券商。</p>
    <form onSubmit={event=>void review(event)}><div className="live-side-switch"><button type="button" className={side==='BUY'?'active':''} onClick={()=>onSideChange('BUY')}>買進 BUY</button><button type="button" className={side==='SELL'?'active':''} onClick={()=>onSideChange('SELL')}>賣出 SELL</button></div>
      <div className="live-side-switch"><button type="button" className={orderType==='MARKET'?'active':''} onClick={()=>setOrderType('MARKET')}>市價</button><button type="button" className={orderType==='LIMIT'?'active':''} onClick={()=>setOrderType('LIMIT')}>限價</button></div>
      <label>手數 Lot<input type="number" min="0.01" max="100" step="0.01" value={lot} required onChange={event=>setLot(event.target.value)}/></label>
      {orderType==='LIMIT'&&<label>指定限價<input type="number" min="0.01" step="0.01" value={limit} required onChange={event=>setLimit(event.target.value)}/></label>}
      <div className="two-fields"><label>停損（選填）<input type="number" min="0.01" step="0.01" value={sl} onChange={event=>setSl(event.target.value)}/></label><label>停利（選填）<input type="number" min="0.01" step="0.01" value={tp} onChange={event=>setTp(event.target.value)}/></label></div>
      <button className="primary full" disabled={busy||!tradeReady}>{busy?'核對中…':'檢查 DEMO 委託'}</button>
    </form>
    {!tradeReady&&<p className="fine">等待 5 秒內的最新 tick、DEMO 帳戶、交易權限與券商商品規格；未就緒時禁止送單。</p>}
    {error&&<p className="modal-error" role="alert">{error}</p>}
    <dialog ref={dialog} className="review-dialog" onCancel={event=>{event.preventDefault();void cancel();}} aria-label="確認 DEMO 委託">{draft&&<><div className="dialog-heading"><h2>核對 cTrader DEMO 草稿</h2><button disabled={busy} onClick={()=>void cancel()} aria-label="關閉 DEMO 草稿">×</button></div><div className="dialog-body">
      <p><strong>{draft.side} {draft.lot} 手 · {draft.order_type==='LIMIT'?'限價':'市價'}</strong> · 擬進場價 {draft.price}</p>
      <p>停損 {draft.sl??'未設定'} · 停利 {draft.tp??'未設定'} · 帳戶：cTrader DEMO</p>
      <p>總曝險手數 {draft.risk.before_lot} → {draft.risk.after_lot}；本筆停損情境損失 {draft.risk.stop_loss_usd??'未設定'} USD</p>
      <p>已收盤面案例：{draft.retrieval.comparison?.method==='context_contract_v1'?'情境規則':draft.retrieval.comparison?.method==='dual_path_structure_v1'?'雙週期對照':'原法三週期'} {draft.retrieval.total} 群；{draft.retrieval.comparison?.reason??'尚未校準相似門檻。'}</p>
      <PoolEvidence pool={draft.retrieval}/>
      <DraftCaseAssistant key={draft.id} draftId={draft.id}/>
      <div className="limitations">{draft.risk.warnings.map((warning,index)=><p key={index}>{warning}</p>)}</div>
      {result&&<div role="status"><strong>{resultLabel(result.status)}</strong><p>券商委託 ID：{result.order_id??'尚未回報'}{result.execution_price?` · 成交價 ${result.execution_price}`:''}</p>{result.error_code&&<p>券商錯誤碼：{result.error_code}</p>}</div>}
      {error&&<p className="modal-error" role="alert">{error}</p>}
    </div><div className="dialog-actions"><button disabled={busy} onClick={()=>void cancel()}>{result?'關閉':'取消草稿'}</button>{result?<button className="primary" disabled={busy} onClick={()=>{void cancel().then(()=>document.getElementById('broker-account-panel')?.scrollIntoView({block:'start',behavior:'auto'}));}}>查看持倉與紀錄</button>:<button className="primary" disabled={busy} onClick={()=>void confirm()}>{busy?'等待券商回報…':'確認送出 DEMO 委託'}</button>}</div></>}</dialog>
  </section>;
}
