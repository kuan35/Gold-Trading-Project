import Decimal from 'decimal.js';
import type {State} from './types';

export default function ReplayAccountSummary({state,onPositions,onHistory,onClose,busy=false}:{state:State|null;onPositions:()=>void;onHistory:()=>void;onClose?:(id:string)=>void;busy?:boolean}){
 const positions=state?.positions??[];
 const total=state?positions.reduce((sum,p)=>sum.plus(p.pnl),new Decimal(0)):null;
 return <div className="assistant-context-block replay-account-summary">
  <strong>本機回放持倉 <span>{positions.length} 筆</span></strong>
  <p>回放浮動損益 <b className={total?.lt(0)?'negative':'positive'}>{total?.toFixed(2)??'—'} USD</b></p>
  <p className="fine">隨回放推進更新；與券商 DEMO 即時損益分開。</p>
  {positions.slice(0,3).map(p=><div key={p.id} className="replay-position-line"><span>{p.side==='BUY'?'買進':'賣出'} {p.lot} 手 · 進場 {p.entry}</span><b className={p.pnl.startsWith('-')?'negative':'positive'}>{p.pnl} USD</b>{onClose&&<button disabled={busy||state?.mode!=='replay'} onClick={()=>onClose(p.id)} aria-label={`平倉本機部位 ${p.id}`}>平倉</button>}</div>)}
  {!positions.length&&<p>目前沒有本機回放持倉。</p>}
  {positions.length>3&&<p className="fine">另有 {positions.length-3} 筆，點下方查看全部。</p>}
  <div className="replay-account-links"><button onClick={onPositions}>查看持倉與損益</button><button onClick={onHistory}>下單與成交紀錄</button></div>
 </div>;
}
