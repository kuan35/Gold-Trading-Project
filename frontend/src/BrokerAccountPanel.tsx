import {useState} from 'react';
import Decimal from 'decimal.js';
import type {DemoMarket} from './demoMarket';
import {useBrokerActivity,type BrokerActivity,type BrokerHistory,type BrokerRecord} from './brokerActivity';
import BrokerClosePanel from './BrokerClosePanel';

type Tab='positions'|'pending'|'history';
const statusLabel=(status:string)=>({ACCEPTED:'已接受，待成交',PARTIALLY_FILLED:'部分成交',FILLED:'已成交',
 CANCELLED:'已取消',REJECTED:'已拒絕',EXPIRED:'已過期',UNKNOWN:'回報待核對',ERROR:'回報錯誤',MISSED:'未成交'}[status]??'狀態待核對');
const orderLabel=(kind?:string|null)=>({MARKET:'市價',LIMIT:'限價',STOP:'停損觸發',PROTECTION:'保護單',STOP_LIMIT:'停損限價',MARKET_RANGE:'區間市價'}[kind??'']??'—');
const sideLabel=(side?:string|null)=>side==='BUY'?'買進':side==='SELL'?'賣出':'—';
const time=(value?:string|null)=>value?`${value.replace('T',' ').replace(/\.\d+(?=Z|[+-])/, '').replace(/\+00:00|Z$/,'')} UTC`:'—';
const number=(value?:string|null)=>{try{const n=value!=null?new Decimal(value):null;return n?.isFinite()?n.toFixed(Math.max(2,n.decimalPlaces())):'—';}catch{return '—';}};
const color=(value?:string|null)=>{try{return value!=null&&new Decimal(value).lt(0)?'negative':value!=null?'positive':'';}catch{return '';}};
const fresh=(status?:string)=>status==='CURRENT';

function HistoryNotice({history}:{history?:BrokerHistory}){
 return <>{!history||history.status==='LOADING'?<p className="fine">正在向券商讀取紀錄…</p>:history.status!=='CURRENT'?<p role="status" className="fine">券商紀錄未就緒或已過期，以下若有資料為最後快照。</p>:null}
  {history?.has_more&&<p className="fine">尚有更多券商紀錄；此快照只顯示最近 30 天、最多 500 筆，請至 cTrader 查看完整帳戶歷史。</p>}</>;
}

function OrdersTable({items,submitted=false,currency}:{items:BrokerRecord[];submitted?:boolean;currency:string}){
 return <div className="table-scroll"><table><thead><tr><th>時間／訂單編號</th><th>操作</th><th>方向</th><th>委託類型</th><th>手數</th><th>指定價</th><th>成交價</th><th>最後回報</th></tr></thead>
  <tbody>{items.map((r,i)=><tr key={r.draft_id??r.id??i} data-status={r.status}><td>{time(r.created_at_utc)}<small>{r.order_id??r.client_order_id??'尚無券商編號'}{r.account_scope==='UNKNOWN'?' · 舊紀錄帳戶未標記':''}</small></td>
   <td>{r.intent==='CLOSE'?'平倉':r.intent==='OPEN'?'進場／加倉':'—'}{r.position_id&&<small>部位 {r.position_id}</small>}</td><td>{submitted&&r.intent==='CLOSE'?'原':''}{sideLabel(r.side)}</td><td>{orderLabel(r.order_type)}</td><td>{r.lot??'—'}{r.filled_lot!=null&&<small>已成交 {r.filled_lot}</small>}</td>
   <td>{r.limit_price??(submitted&&r.order_type==='MARKET'?'市價':r.price)??'—'}</td><td>{r.execution_price??'—'}</td>
   <td>{statusLabel(r.status)}{r.status==='UNKNOWN'&&<small>請至 cTrader 核對，勿重送</small>}{r.error_code&&<small>{r.error_code}</small>}</td></tr>)}</tbody>
 </table>{!items.length&&<p className="broker-empty">{submitted?'尚無本工作台已送出的 DEMO 委託；草稿未確認不會出現在送單紀錄。':'此範圍目前沒有可顯示的券商訂單。'}</p>}<span className="sr-only">帳戶幣別 {currency}</span></div>;
}

export function BrokerAccountView({market,activity,tab,error='',onTab=()=>{},onPage=()=>{}}:{market:DemoMarket|null;activity:BrokerActivity|null;tab:Tab;error?:string;onTab?:(tab:Tab)=>void;onPage?:(offset:number)=>void}){
 const a=market?.account,currency=a?.currency??'幣別未確認';
 const accountFresh=market?.connection_status==='CONNECTED'&&fresh(a?.status);
 const pnlFresh=accountFresh&&fresh(a?.pnl_status);
 const positions=a?.positions??[],pending=a?.pending_orders??[];
 const submitted=activity?.submissions;
 return <section className="broker-account-workspace" id="broker-account-panel" aria-label="cTrader DEMO 持倉與交易紀錄">
  <header className="broker-account-heading"><div><h2>DEMO 帳戶與交易紀錄</h2><p className="fine">cTrader DEMO · {currency} · 與本機回放帳戶分開</p></div>
   <span role="status">{accountFresh?'帳戶已同步':a?'帳戶資料已過期':'等待券商帳戶／未連線'}</span></header>
  <dl className="broker-account-totals"><div><dt>餘額</dt><dd>{number(a?.balance)} {currency}</dd></div>
   <div><dt>帳戶淨值</dt><dd>{number(pnlFresh?a?.equity:null)} {currency}</dd></div>
   <div><dt>全部商品浮動淨損益</dt><dd className={color(pnlFresh?a?.net_unrealized_pnl:null)}>{number(pnlFresh?a?.net_unrealized_pnl:null)} {currency}</dd></div>
   <div><dt>黃金持倉浮動淨損益</dt><dd className={color(pnlFresh?a?.xau_net_unrealized_pnl:null)}>{number(pnlFresh?a?.xau_net_unrealized_pnl:null)} {currency}</dd></div></dl>
  <p className="broker-pnl-note fine">{pnlFresh?'券商損益約每 2 秒取樣':a?.pnl_status==='STALE'?'損益已過期，等待券商重新更新':'損益尚未就緒或正在更新'} · 損益快照 {time(a?.pnl_updated_at_utc)}。浮動淨損益不含潛在平倉佣金。</p>
  {error&&<p className="broker-read-error" role="alert">{error}</p>}
  <div className="tabs broker-account-tabs" role="tablist" aria-label="DEMO 帳戶資料">{[['positions',`持倉與損益 ${positions.length}`],['pending',`待成交 ${pending.length}`],['history','下單與成交紀錄']].map(([key,label])=>
   <button key={key} id={`broker-tab-${key}`} role="tab" aria-selected={tab===key} aria-controls="broker-account-content" className={tab===key?'active':''} onClick={()=>onTab(key as Tab)}>{label}</button>)}</div>
  <div id="broker-account-content" role="tabpanel" aria-labelledby={`broker-tab-${tab}`}>
   {tab==='positions'&&<div className="table-scroll"><table><thead><tr><th>部位／時間</th><th>方向</th><th>手數</th><th>進場均價</th><th>目前可平倉價</th><th>停損</th><th>停利</th><th>浮動毛損益 {currency}</th><th>浮動淨損益 {currency}</th><th>操作</th></tr></thead>
    <tbody>{positions.map(p=><tr key={p.id}><td>{p.id}<small>{time(p.opened_at_utc)}</small></td><td>{sideLabel(p.side)}</td><td>{p.lot??'—'}</td><td>{p.entry??'—'}</td>
     <td>{market?.quote.status==='CURRENT'&&market.quote.age_seconds!=null&&market.quote.age_seconds<=5?market.quote[p.side==='BUY'?'bid':'ask']??'—':'—'}</td><td>{p.sl??'—'}</td><td>{p.tp??'—'}</td>
     <td className={color(pnlFresh?p.gross_pnl:null)}>{number(pnlFresh?p.gross_pnl:null)}</td><td className={color(pnlFresh?p.net_pnl:null)}>{number(pnlFresh?p.net_pnl:null)}</td><td><BrokerClosePanel market={market} positionId={p.id}/></td></tr>)}</tbody></table>
    {!positions.length&&<p className="broker-empty">{accountFresh?'目前沒有 XAUUSD DEMO 持倉。券商成交並同步後會在此顯示逐筆損益。':'等待有效帳戶快照，不能判定目前是否有持倉。'}</p>}</div>}
   {tab==='pending'&&<div className="table-scroll"><table><thead><tr><th>訂單／時間</th><th>方向</th><th>類型</th><th>手數</th><th>指定價</th><th>停損</th><th>停利</th><th>狀態</th></tr></thead>
    <tbody>{pending.map(p=><tr key={p.id}><td>{p.id}<small>{time(p.created_at_utc)}</small></td><td>{sideLabel(p.side)}</td><td>{orderLabel(p.order_type)}</td><td>{p.lot??'—'}</td><td>{p.limit_price??'—'}</td><td>{p.sl??'—'}</td><td>{p.tp??'—'}</td><td>待成交{p.status==='PARTIALLY_FILLED'?'／部分成交':''}</td></tr>)}</tbody></table>
    {!pending.length&&<p className="broker-empty">{accountFresh?'目前沒有 XAUUSD DEMO 待成交委託。':'等待券商帳戶快照。'}</p>}</div>}
   {tab==='history'&&<div className="broker-history-content"><h3>本工作台已送委託</h3><p className="fine">保存在本機，重新整理仍可查看。以下是最後確認的券商回報，已接受不等於已成交。</p>
    {submitted?<><OrdersTable items={submitted.items} submitted currency={currency}/><div className="broker-history-pages"><span>第 {submitted.items.length?submitted.offset+1:0}–{Math.min(submitted.offset+submitted.items.length,submitted.total)} 筆／共 {submitted.total} 筆</span>
     <button disabled={submitted.offset===0} onClick={()=>onPage(Math.max(0,submitted.offset-submitted.limit))}>上一頁</button><button disabled={!submitted.has_more} onClick={()=>onPage(submitted.offset+submitted.limit)}>下一頁</button></div></>:<p>正在讀取本機送單紀錄…</p>}
    <h3>券商最近 30 天訂單</h3><HistoryNotice history={activity?.broker_orders}/><OrdersTable items={activity?.broker_orders.items??[]} currency={currency}/>
    <h3>券商成交明細</h3><p className="fine">每次部分成交可各有一筆；平倉顯示已實現毛損益，佣金與隔夜費另列，不能直接當作淨損益。</p><HistoryNotice history={activity?.broker_deals}/>
    <div className="table-scroll"><table><thead><tr><th>成交時間／編號</th><th>方向</th><th>進出場</th><th>手數</th><th>成交價</th><th>狀態</th><th>已實現毛損益 {currency}</th><th>佣金</th><th>隔夜費</th></tr></thead>
     <tbody>{activity?.broker_deals.items.map(r=><tr key={r.id}><td>{time(r.executed_at_utc)}<small>{r.id} · 訂單 {r.order_id??'—'}</small></td><td>{sideLabel(r.side)}</td><td>{['FILLED','PARTIALLY_FILLED'].includes(r.status)?r.role==='CLOSE'?'平倉成交':'進場成交':'未確認成交'}</td><td>{r.lot??'—'}</td><td>{r.execution_price??'—'}</td><td>{statusLabel(r.status)}</td><td className={color(r.realized_gross_pnl)}>{number(r.realized_gross_pnl)}</td><td>{number(r.commission)}</td><td>{number(r.swap)}</td></tr>)}</tbody></table>
     {!activity?.broker_deals.items.length&&<p className="broker-empty">此範圍尚無可顯示的券商成交。</p>}</div>
   </div>}
  </div>
 </section>;
}

export default function BrokerAccountPanel({market}:{market:DemoMarket|null}){
 const [tab,setTab]=useState<Tab>('positions'),[offset,setOffset]=useState(0);
 const {activity,error}=useBrokerActivity(offset);
 return <BrokerAccountView market={market} activity={activity} error={error} tab={tab} onTab={setTab} onPage={setOffset}/>;
}
