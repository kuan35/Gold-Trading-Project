type Props={id:string;ready:boolean;checking:boolean;locked:boolean;missing:string[];error?:string;onCheck:()=>void};
export default function TicketCheckAction({id,ready,checking,locked,missing,error,onCheck}:Props){
 return <div className="cw-ticket-action">
  <button type="button" className="primary full" aria-describedby={id+'-hint'} disabled={checking||locked||!ready} onClick={onCheck}>{checking?'讀取最新盤面並核對…':'檢查 DEMO 委託'}</button>
  <p id={id+'-hint'} className="fine">{missing.length?'待填：'+missing.join('、'):'檢查後核對風險，再由你確認送出。'}</p>
  {!ready&&<p className="fine">等待最新 DEMO 報價與帳戶連線。</p>}
  {error&&<p role="alert" className="modal-error">{error}</p>}
 </div>;
}
