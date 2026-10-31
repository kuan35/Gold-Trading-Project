import {useEffect,useRef,useState,useId} from 'react';import type {ArchiveEntry} from './deskConversations';
export default function ConversationHistoryActions({entry,busy,onRename,onDelete}:{entry:ArchiveEntry;busy:boolean;onRename?:(id:string,title:string)=>void;onDelete?:(id:string)=>void}){
 const ref=useRef<HTMLDialogElement>(null),heading=useId();const [title,setTitle]=useState(entry.title),[deleting,setDeleting]=useState(false),[error,setError]=useState('');
 useEffect(()=>setTitle(entry.title),[entry.title]);
 const close=()=>{ref.current?.close();setDeleting(false);setError('');};
 return <><button className="pd-history-manage" type="button" disabled={busy} aria-label={'管理對話 '+entry.title} onClick={()=>{setTitle(entry.title);setDeleting(false);ref.current?.showModal();}}>⋯</button>
 <dialog ref={ref} className="review-dialog history-dialog" aria-labelledby={heading} onCancel={e=>{e.preventDefault();close();}}><div className="dialog-heading"><h2 id={heading}>{deleting?'刪除這段對話？':'管理對話'}</h2><button type="button" aria-label="關閉對話管理" onClick={close}>×</button></div>
 {deleting?<div className="dialog-body"><p>「{entry.title}」將從此瀏覽器移除，刪除後無法復原。這不會取消任何交易委託。</p></div>:<div className="dialog-body"><label>對話名稱<input maxLength={48} value={title} onChange={e=>setTitle(e.target.value)}/></label>{error&&<p role="alert">{error}</p>}</div>}
 <div className="dialog-actions"><button type="button" onClick={close}>取消</button>{deleting?<button type="button" disabled={busy} onClick={()=>{onDelete?.(entry.id);close();}}>確認刪除此對話</button>:<><button type="button" disabled={busy||!onDelete} onClick={()=>setDeleting(true)}>刪除對話</button><button className="primary" type="button" disabled={busy||!onRename} onClick={()=>{if(!title.trim()){setError('請輸入對話名稱。');return;}onRename?.(entry.id,title);close();}}>儲存名稱</button></>}</div></dialog></>;
}
