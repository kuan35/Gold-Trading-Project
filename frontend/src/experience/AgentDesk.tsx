import {useEffect,useMemo,useRef,useState,type ReactNode,type CSSProperties} from 'react';
import {motion,AnimatePresence} from 'motion/react';
import {SHORTCUT} from './platform';
import type {DemoMarket} from '../demoMarket';
import {useLiveCandles} from '../useLiveCandles';import {mergeLiveBars,type LiveChartFrame} from '../liveCandles';
import LiveCandleChart from '../LiveCandleChart';import {DeskIcon} from '../DeskChrome';import AnimatedPrice from './AnimatedPrice';
import type {DraftChartState} from '../DraftChartOverlay';
export function AgentOrb({busy,size=44}:{busy:boolean;size?:number}){
 return <span className={`ag-orb ${busy?'ag-orb-busy':''}`} style={{width:size,height:size}} aria-hidden="true"><i/><b/></span>;
}


export function MiniChart({light,draft}:{light:boolean;draft?:DraftChartState}){
 const [interval,setInterval]=useState<'5m'|'15m'|'1h'>('5m');
 const {frame,pending}=useLiveCandles(interval);
 const bars=useMemo(()=>mergeLiveBars(frame?.bars??[],frame?.status==='CURRENT'?frame.forming?.pending_bars??[]:[],frame?.status==='CURRENT'?frame.forming?.bar??null:null),[frame]);
 return <div className="ag-mini-chart"><div className="ag-seg">{(['5m','15m','1h'] as const).map(k=><button key={k} type="button" aria-pressed={interval===k} onClick={()=>setInterval(k)}>{k==='5m'?'5 分':k==='15m'?'15 分':'1 小時'}</button>)}</div>
  <LiveFrameStatus frame={frame} pending={pending}/>
  {draft?.side&&<p className="fine">圖上價位屬於目前草稿；拖曳只改欄位，仍需重新檢查。市價進場隨報價。</p>}
  {bars.length?<LiveCandleChart key={interval} bars={bars} light={light} interval={interval} draft={draft?{...draft,disabled:draft.disabled||frame?.status!=='CURRENT'}:undefined}/>:<p className="ag-empty">{pending?'載入即時 K 線…':'即時 K 線未就緒'}</p>}</div>;
}

export function LiveFrameStatus({frame,pending}:{frame:LiveChartFrame|null;pending:boolean}){
 const bar=frame?.status==='CURRENT'?frame.forming:null,last=frame?.bars.at(-1);
 return <div className="ag-mini-status"><p role="status">{frame?.status==='STALE'?'資料已過期，保留最後快照；不是目前即時狀態。':frame?.status==='CURRENT'?(bar?`形成中${bar.partial?'（本機觀測未滿整根）':''}`:'已收棒快照，等待形成中 K 線。'):pending?'載入即時 K 線…':'即時資料尚未就緒。'}</p>
 {last&&<small>最新已收棒起點 {new Date(last.time*1000).toISOString().replace('T',' ').replace('.000Z',' UTC')}</small>}
 {bar&&<small>形成棒更新 {new Date(bar.updated_at_ms).toLocaleTimeString('zh-TW',{hour12:false})} · 本機接收 tick {bar.bar.volume}</small>}
 <small>量柱為券商 tick 量；形成棒為本機接收筆數，並非集中市場成交量。</small></div>;
}

export type ReplayBar={bid:string;ask:string;equity:string;balance:string;positions:number;clock:string};
export function AgentTopbar({market,light,onTheme,drawerOpen=false,onDrawer,title,replay}:{market:DemoMarket|null;light:boolean;onTheme:()=>void;drawerOpen?:boolean;onDrawer?:()=>void;title?:string;replay?:ReplayBar|null}){
 if(replay)return <header className="ag-topbar ag-topbar-replay">
  {title&&<h1 className="ag-page-title">{title}</h1>}
  <div className="ag-sym"><strong>XAUUSD</strong><small>回放行情</small></div>
  <div className="ag-quote"><small>BID</small><AnimatedPrice className="ag-bid" value={replay.bid}/></div>
  <div className="ag-quote"><small>ASK</small><AnimatedPrice className="ag-ask" value={replay.ask}/></div>
  <span className="ag-live ag-replay" data-tip="目前回放到的歷史時間；按 → 推進一根 K 棒"><i/><span className="ag-replay-full">回放 {replay.clock.replace(' UTC','')}</span><span className="ag-replay-short">{replay.clock.slice(5,16)}</span></span>
  <div className="ag-spacer"/>
  <div className="ag-acct"><small>模擬淨值</small><strong><AnimatedPrice value={replay.equity}/></strong></div>
  <div className="ag-acct"><small>模擬餘額</small><strong><AnimatedPrice value={replay.balance}/></strong></div>
  <div className="ag-acct"><small>模擬持倉</small><strong>{replay.positions}</strong></div>
  <button type="button" className="ag-icon-btn ag-kbd-btn" aria-label="開啟指令面板" data-tip={`指令面板：快速切頁與推進 K 棒（${SHORTCUT}）`} onClick={()=>window.dispatchEvent(new Event('gd:palette'))}><svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg><span>指令</span><kbd>{SHORTCUT}</kbd></button>
  <button type="button" className="ag-icon-btn" aria-label={light?'切換深色':'切換淺色'} data-tip={light?'切換成深色主題':'切換成淺色主題'} onClick={onTheme}><DeskIcon name="sun"/></button>
 </header>;
 const q=market?.quote,a=market?.account,live=market?.connection_status==='CONNECTED'&&q?.status==='CURRENT'&&typeof q.age_seconds==='number'&&q.age_seconds>=0&&q.age_seconds<=5&&Number(q.bid)>0&&Number(q.ask)>=Number(q.bid);
 const acct=a?.status==='CURRENT'&&a.pnl_status==='CURRENT',pnl=Number(a?.xau_net_unrealized_pnl);
 return <header className="ag-topbar">
  {title&&<h1 className="ag-page-title">{title}</h1>}
  <div className="ag-sym"><strong>XAUUSD</strong><small>現貨黃金</small></div>
  <div className="ag-quote"><small>BID</small><AnimatedPrice className="ag-bid" value={live?q?.bid:null}/></div>
  <div className="ag-quote"><small>ASK</small><AnimatedPrice className="ag-ask" value={live?q?.ask:null}/></div>
  <span className={`ag-live ${live?'':'ag-off'}`} data-tip={live?'cTrader DEMO 即時報價，延遲 '+(q?.age_seconds??0).toFixed(1)+' 秒':'正在連線券商'}><i/>{live?'即時':'等待即時報價'}</span>
  <div className="ag-spacer"/>
  <div className="ag-acct"><small>DEMO 淨值</small><strong><AnimatedPrice value={acct?a?.equity:null}/></strong></div>
  <div className="ag-acct"><small>黃金浮動</small><strong className={Number.isFinite(pnl)?(pnl>=0?'ag-up':'ag-down'):''}><AnimatedPrice value={acct?a?.xau_net_unrealized_pnl:null}/></strong></div>
  <div className="ag-acct"><small>持倉</small><strong>{acct?a?.positions.length:'—'}</strong></div>
  <button type="button" className="ag-icon-btn ag-kbd-btn" aria-label="開啟指令面板" data-tip={`指令面板：快速切頁與推進 K 棒（${SHORTCUT}）`} onClick={()=>window.dispatchEvent(new Event('gd:palette'))}><svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg><span>指令</span><kbd>{SHORTCUT}</kbd></button>
  <button type="button" className="ag-icon-btn" aria-label={light?'切換深色':'切換淺色'} data-tip={light?'切換成深色主題':'切換成淺色主題'} onClick={onTheme}><DeskIcon name="sun"/></button>
  {onDrawer&&<button type="button" className={`ag-icon-btn ${drawerOpen?'ag-on':''}`} aria-label={drawerOpen?'收合側欄':'展開側欄'} data-tip={drawerOpen?'收合右側工作區':'展開右側下單、即時圖與帳戶'} onClick={onDrawer}><DeskIcon name="chart"/></button>}
 </header>;
}

export type DeskPage='assistant'|'live'|'replay';
export function AgentRail({active='assistant',busy,onNavigate,onNew,onHistory}:{active?:DeskPage;busy:boolean;onNavigate:(v:DeskPage)=>void;onNew?:()=>void;onHistory?:()=>void}){
 const item=(icon:Parameters<typeof DeskIcon>[0]['name'],label:string,on:()=>void,selected=false)=><button type="button" className={`ag-rail-btn ${selected?'ag-on':''}`} disabled={busy&&!selected} onClick={on} aria-label={label} aria-current={selected?'page':undefined} data-tip={label} data-tip-side="right">
  {selected&&<motion.span layoutId="ag-rail-pill" className="ag-rail-pill" transition={{type:'spring',stiffness:420,damping:34}}/>}<DeskIcon name={icon}/></button>;
 return <nav className="ag-rail" aria-label="工作台頁面"><span className="ag-mark">GD</span>
  {item('chat','交易對話',()=>onNavigate('assistant'),active==='assistant')}{item('chart','即時看盤',()=>onNavigate('live'),active==='live')}{item('replay','歷史回放',()=>onNavigate('replay'),active==='replay')}
  <span className="ag-rail-gap"/>{onNew&&item('plus','新對話',onNew)}{onHistory&&item('arrow','對話紀錄',onHistory)}{item('sun','助手與模型設定',()=>{onNavigate('assistant');window.dispatchEvent(new Event('gd:settings'));})}
 </nav>;
}
// The rail lives in the route frame; the conversation listens for its commands.
export const RAIL_EVENT='gd:rail';
export const railCommand=(command:'new'|'history')=>window.dispatchEvent(new CustomEvent(RAIL_EVENT,{detail:command}));

// Floating entry back to the agent from the market pages.
export function AskAgent({onOpen}:{onOpen:()=>void}){
 return <motion.button type="button" className="ag-ask-agent" onClick={onOpen} initial={{opacity:0,y:20}} animate={{opacity:1,y:0}} transition={{delay:.3,type:'spring',stiffness:260,damping:24}}><AgentOrb busy={false} size={30}/><span><strong>問 Agent</strong><small>根據目前盤面討論多空與下單</small></span><kbd>G C</kbd></motion.button>;
}

