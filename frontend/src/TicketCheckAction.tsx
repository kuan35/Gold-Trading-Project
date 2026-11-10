type Props={id:string;ready:boolean;checking:boolean;locked:boolean;missing:string[];error?:string;onCheck:()=>void;environment?:'demo'|'live'};
export default function TicketCheckAction({id,ready,checking,locked,missing,error,onCheck,environment='demo'}:Props){
 return <div className="cw-ticket-action">
  <button type="button" className="primary full" aria-describedby={id+'-hint'} disabled={checking||locked||!ready} onClick={onCheck}>{checking?'讀取最新盤面並核對…':`檢查 ${environment.toUpperCase()} 委託`}</button>
  <p id={id+'-hint'} className="fine">{missing.length?'待填：'+missing.join('、'):'核對這筆草稿的價位與風險，再請所選助手評估；尚未送單。'}</p>
  {!ready&&<p className="fine">等待最新 {environment.toUpperCase()} 報價、帳戶、交易權限與本機風險設定。</p>}
  {error&&<p role="alert" className="modal-error">{error}</p>}
 </div>;
}
