import {useEffect,useRef,useState} from 'react';import {api,key} from './api';import type {Position,State} from './types';
type Draft={id:string;revision:number;kind:string;limit_price?:string;sl?:string|null;tp?:string|null};
export default function ReplayPositionActions({position,onUpdate,disabled}:{position:Position;onUpdate:(state:State)=>void;disabled:boolean}){
 const [open,setOpen]=useState(false),[kind,setKind]=useState<'LIMIT'|'PROTECT'>('LIMIT'),[limit,setLimit]=useState(''),[sl,setSl]=useState(position.sl??''),[tp,setTp]=useState(position.tp??'');
 const [draft,setDraft]=useState<Draft|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const dialog=useRef<HTMLDialogElement>(null),guard=useRef(false),confirmKey=useRef('');
 useEffect(()=>{if(open)dialog.current?.showModal();else dialog.current?.close();},[open]);
 const review=async()=>{if(guard.current)return;guard.current=true;setBusy(true);setError('');try{
  setDraft(await api<Draft>(`/positions/${position.id}/management-draft`,{kind,limit_price:kind==='LIMIT'?limit:null,changes:kind==='PROTECT'?{sl:sl.trim()||null,tp:tp.trim()||null}:{}}));confirmKey.current=key();
 }catch(e){setError(e instanceof Error?e.message:'無法建立草稿');}finally{guard.current=false;setBusy(false);}};
 const close=async()=>{if(busy)return;if(draft)await api(`/drafts/${draft.id}/cancel`,{}).catch(()=>{});setOpen(false);setDraft(null);};
 const confirm=async()=>{if(!draft||guard.current)return;guard.current=true;setBusy(true);try{
  const r=await api<{state:State}>(`/positions/management/${draft.id}/confirm`,{revision:draft.revision,idempotency_key:confirmKey.current});onUpdate(r.state);setOpen(false);setDraft(null);
 }catch(e){setError(e instanceof Error?e.message:'操作未完成；相同草稿可核對後重試');}finally{guard.current=false;setBusy(false);}};
 return <><button disabled={disabled} onClick={()=>{setKind('LIMIT');setSl(position.sl??'');setTp(position.tp??'');setDraft(null);setError('');setOpen(true);}}>限價平倉／保護</button>
 <dialog ref={dialog} className="review-dialog" aria-label="本機原部位管理" onCancel={e=>{e.preventDefault();void close();}}><div className="dialog-heading"><h2>本機回放 · 原部位管理</h2></div><div className="dialog-body"><p>{position.side} {position.lot}手 · 部位 {position.id}</p>
 {!draft?<><label>操作<select value={kind} onChange={e=>setKind(e.target.value as typeof kind)}><option value="LIMIT">掛指定價等待平倉</option><option value="PROTECT">修改停損／停利</option></select></label>{kind==='LIMIT'?<label>限價平倉價<input inputMode="decimal" value={limit} onChange={e=>setLimit(e.target.value)}/></label>:<><label>停損（清空表示移除）<input inputMode="decimal" value={sl} onChange={e=>setSl(e.target.value)}/></label><label>停利（清空表示移除）<input inputMode="decimal" value={tp} onChange={e=>setTp(e.target.value)}/></label></>}</>:<p>{kind==='LIMIT'?`確認以 ${draft.limit_price} 掛單平掉這筆原部位，觸價前不成交。`:`確認修改：停損 ${draft.sl??'移除'}；停利 ${draft.tp??'移除'}。`}</p>}
 {error&&<p role="alert">{error}</p>}</div><div className="dialog-actions"><button disabled={busy} onClick={()=>void close()}>取消</button><button disabled={busy||disabled} onClick={()=>void(draft?confirm():review())}>{draft?'確認本機變更':'檢查變更'}</button></div></dialog></>;
}
