import {useEffect,useRef,useState} from 'react';
import {api,key} from './api';
import type {DemoMarket} from './demoMarket';
import {brokerCloseReady,confirmBrokerClose,CloseConfirmError} from './BrokerClosePanel';
type Choice='KEEP'|'SET'|'CLEAR';
export function protectionChanges(sl:Choice,slValue:string,tp:Choice,tpValue:string){
 const changes:Record<string,string|null>={};
 for(const [field,choice,value] of [['sl',sl,slValue],['tp',tp,tpValue]]){
  if(choice==='CLEAR')changes[field]=null;
  if(choice==='SET'){if(!value.trim())throw new Error('請填寫指定價格');changes[field]=value.trim();}
 }
 if(!Object.keys(changes).length)throw new Error('請選擇要變更的停損或停利');
 return changes;
}
type Draft={id:string;revision:number;position_id:string;sl:string|null;tp:string|null;order_id?:string;explanation:string};
export default function BrokerPositionActions({market,positionId,orderId}:{market:DemoMarket|null;positionId:string;orderId?:string}){
 const [open,setOpen]=useState(false),[draft,setDraft]=useState<Draft|null>(null),[busy,setBusy]=useState(false),[message,setMessage]=useState('');
 const [sl,setSl]=useState<Choice>('KEEP'),[tp,setTp]=useState<Choice>('KEEP'),[sv,setSv]=useState(''),[tv,setTv]=useState('');
 const [result,setResult]=useState<{status:string;status_observed_at_utc?:string}|null>(null);
 const dialog=useRef<HTMLDialogElement>(null),working=useRef(false),confirmKey=useRef('');
 const ready=brokerCloseReady(market,positionId),position=market?.account?.positions.find(p=>p.id===positionId);
 const locked=Boolean(result&&(['UNKNOWN','ACCEPTED','PARTIALLY_FILLED'].includes(result.status)||result.status==='APPLIED'&&!(Date.parse(market?.account?.updated_at_utc??'')>Date.parse(result.status_observed_at_utc??''))));
 useEffect(()=>{if(open)dialog.current?.showModal();else dialog.current?.close();},[open]);
 useEffect(()=>{if(!draft||!result||!['UNKNOWN','ACCEPTED','PARTIALLY_FILLED'].includes(result.status))return;
  let active=true;const timer=window.setInterval(()=>{void api<{status:string;status_observed_at_utc?:string}>(`/broker/drafts/${draft.id}/status`).then(r=>{if(active)setResult(r);}).catch(()=>{});},2500);
  return()=>{active=false;clearInterval(timer);};
 },[draft?.id,result?.status]);
 const review=async()=>{if(working.current||locked)return;working.current=true;setBusy(true);setMessage('');
  try{const endpoint=orderId?`/broker/pending/${encodeURIComponent(orderId)}/cancel-draft`:`/broker/positions/${encodeURIComponent(positionId)}/protection-draft`;
   const next=await api<Draft>(endpoint,orderId?{}:protectionChanges(sl,sv,tp,tv));setDraft(next);confirmKey.current=key();
  }catch(e){setMessage(e instanceof Error?e.message:'無法建立草稿');}finally{working.current=false;setBusy(false);}
 };
 const cancel=async()=>{if(working.current)return;if(draft&&!result){try{await api(`/broker/drafts/${draft.id}/cancel`,{});}catch{setMessage('取消草稿失敗，請稍後重試');return;}}setOpen(false);setDraft(null);};
 const confirm=async()=>{if(!draft||working.current||locked)return;working.current=true;setBusy(true);setResult({status:'UNKNOWN'});
  try{setResult(await confirmBrokerClose(draft.id,draft.revision,confirmKey.current));setOpen(false);}
  catch(e){if(e instanceof CloseConfirmError&&e.safeRejected)setResult({status:'REJECTED'});setMessage(e instanceof Error?e.message:'回報待核對，勿重送');}
  finally{working.current=false;setBusy(false);}
 };
 const advanced=position?.trailing_stop_loss||position?.guaranteed_stop_loss;
 return <span className="broker-position-actions"><button disabled={!ready||busy||locked||!!advanced} onClick={()=>{setDraft(null);setResult(null);setMessage('');setOpen(true);}}>{orderId?'取消限價平倉':'修改停損／停利'}</button>
  {advanced&&<small>移動／保證停損請至 cTrader 管理</small>}
  {result&&<small role="status">{({APPLIED:'券商回報保護已更新',CANCELLED:'券商已取消掛單',REJECTED:'未通過或券商拒絕',UNKNOWN:'結果待核對，勿重送'} as Record<string,string>)[result.status]??'等待券商回報'}</small>}
  <dialog ref={dialog} className="review-dialog" onCancel={e=>{e.preventDefault();void cancel();}} aria-label={orderId?'取消限價平倉':'修改停損停利'}><div className="dialog-heading"><h2>{orderId?'取消限價平倉':'修改停損／停利'}</h2></div>
   <div className="dialog-body"><p>原部位 {positionId}{orderId?` · 掛單 ${orderId}`:''}</p>
   {!draft&&!orderId&&<>{([['sl','停損',sl,setSl,sv,setSv],['tp','停利',tp,setTp,tv,setTv]] as const).map(([field,label,choice,setChoice,value,setValue])=><label key={field}>{label}（目前 {position?.[field]??'未設定'}）<select value={choice} onChange={e=>setChoice(e.target.value as Choice)}><option value="KEEP">保留原設定</option><option value="SET">新增／改為指定價</option><option value="CLEAR">移除</option></select>{choice==='SET'&&<input inputMode="decimal" value={value} onChange={e=>setValue(e.target.value)} aria-label={`${label}指定價`}/>}</label>)}</>}
   {draft&&<><p>{draft.explanation}</p>{!orderId&&<p>確認後：停損 {draft.sl??'移除／未設定'} · 停利 {draft.tp??'移除／未設定'}</p>}</>}
   {message&&<p role="alert">{message}</p>}</div><div className="dialog-actions"><button disabled={busy} onClick={()=>void cancel()}>關閉</button>{!draft?<button disabled={busy||!ready||locked} onClick={()=>void review()}>檢查變更</button>:<button className="primary" disabled={busy||!ready||locked} onClick={()=>void confirm()}>確認{orderId?'取消掛單':'修改 DEMO 保護'}</button>}</div></dialog>
 </span>;
}
