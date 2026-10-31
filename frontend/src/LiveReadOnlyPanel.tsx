import {useEffect,useState} from 'react';
import {api} from './api';import Chart from './Chart';import type {Bar} from './types';import type {DemoMarket} from './demoMarket';
type LiveData=Omit<DemoMarket,'source'|'environment'> & {source:'ctrader_live_xauusd';environment:'live';read_only:true;bars:Record<string,Bar[]>};
function Content({light}:{light:boolean}){
 const [data,setData]=useState<LiveData|null>(null),[error,setError]=useState(''),[period,setPeriod]=useState('5m');
 useEffect(()=>{let active=true;let timer:number;
 const load=async()=>{try{const v=await api<LiveData>('/live-readonly');if(v.environment!=='live'||v.read_only!==true||v.order_connection!==false)throw Error('LIVE唯讀狀態無效。');if(active){setData(v);setError('');}}catch(e){if(active){setData(null);setError(e instanceof Error?e.message:'LIVE連線失敗');}}if(active)timer=window.setTimeout(load,2000);};void load();return()=>{active=false;window.clearTimeout(timer);};},[]);
 const account=data?.account;
 return <section className="live-readonly-content" aria-label="LIVE真實帳戶唯讀"><h2>LIVE 真實帳戶 · 唯讀</h2><p>此區使用獨立LIVE連線，與頁首及委託區的DEMO帳戶分開。</p>
 {error&&<p role="alert">{error}</p>}<p>連線：{data?.connection_status??'讀取中'} · BID {data?.quote.bid??'—'} / ASK {data?.quote.ask??'—'} · {data?.quote.status??'—'}</p><p className="fine">報價時間 {data?.quote.source_time_utc??'未提供'} · 帳戶時間 {account?.updated_at_utc??'未提供'}</p>
 {['NOT_CONFIGURED','ACCOUNT_ID_REQUIRED','CREDENTIALS_MISSING','LIVE_ENVIRONMENT_REQUIRED'].includes(data?.connection_status??'')&&<p>請在本機 product/.env.ctrader.live 填入LIVE專用憑證與明確帳戶ID；範本為 .env.ctrader.live.example。</p>}
 <p>餘額 {account?.balance??'—'} · 淨值 {account?.equity??'—'} {account?.currency??''} · 帳戶狀態 {account?.status??'尚未連線'} · 損益狀態 {account?.pnl_status??'未提供'}</p>
 <div role="group" aria-label="LIVE圖表週期">{['5m','15m','1h'].map(p=><button key={p} aria-pressed={period===p} onClick={()=>setPeriod(p)}>{p}</button>)}</div>
 {data?.bars[period]?.length?<Chart bars={data.bars[period]} light={light} ariaLabel={'LIVE唯讀 '+period}/>:<p>尚無LIVE已收K棒。</p>}
 <div className="table-scroll"><table><thead><tr><th>黃金持倉方向</th><th>手數</th><th>進場價</th><th>浮動損益</th></tr></thead><tbody>{account?.positions.map(p=><tr key={p.id}><td>{p.side}</td><td>{p.lot??'—'}</td><td>{p.entry??'—'}</td><td>{p.net_pnl??'未提供'}</td></tr>)}</tbody></table></div><p>待成交 {account?.pending_orders.length??'—'} 筆。此連線不提供開倉、平倉或撤單。</p></section>;
}
export default function LiveReadOnlyPanel({light}:{light:boolean}){
 const [open,setOpen]=useState(false);
 return <section className="live-readonly-panel"><button type="button" aria-expanded={open} onClick={()=>setOpen(v=>!v)}>{open?'收合LIVE唯讀帳戶':'查看LIVE真實帳戶（唯讀）'}</button>{open&&<Content light={light}/>}</section>;
}
