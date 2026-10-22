import {useEffect,useMemo,useRef,useState} from 'react';
import LiveCandleChart from './LiveCandleChart';
import type {DemoMarket} from './demoMarket';
import {useLiveCandles} from './useLiveCandles';
import {mergeLiveBars,provisionalBarCount} from './liveCandles';

export default function LiveChart({light,market}:{light:boolean;market:DemoMarket|null}) {
  const host=useRef<HTMLDivElement>(null);
  const [status,setStatus]=useState<'loading'|'embedded'|'failed'>('loading');
  const [attempt,setAttempt]=useState(0);
  const [interval,setInterval]=useState<'5m'|'15m'|'1h'>('5m');
  const {frame:brokerBars,pending:barsPending}=useLiveCandles(interval);
  const forming=brokerBars?.forming;
  const provisional=provisionalBarCount(brokerBars?.bars??[],forming?.pending_bars??[]);
  const displayBars=useMemo(()=>mergeLiveBars(brokerBars?.bars??[],forming?.pending_bars??[],forming?.bar??null),[brokerBars]);
  const brokerChart=brokerBars?.status==='CURRENT'&&Boolean(brokerBars.bars.length);
  useEffect(()=>{
    if(brokerChart||barsPending)return;
    const target=host.current;if(!target)return;
    setStatus('loading');let active=true;
    const container=document.createElement('div');
    container.className='tradingview-widget-container';
    container.style.height='100%';container.style.width='100%';
    const widget=document.createElement('div');
    widget.className='tradingview-widget-container__widget';
    widget.style.height='100%';widget.style.width='100%';
    container.append(widget);target.replaceChildren(container);
    const timeout=window.setTimeout(()=>{if(active)setStatus('failed');},20000);
    const observer=new MutationObserver(()=>{
      const frame=container.querySelector('iframe');
      if(frame&&active){frame.title='TradingView 黃金即時參考圖表';window.clearTimeout(timeout);setStatus('embedded');observer.disconnect();}
    });
    observer.observe(container,{childList:true,subtree:true});
    const script=document.createElement('script');
    script.src='https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js';
    script.async=true;
    script.textContent=JSON.stringify({autosize:true,symbol:'OANDA:XAUUSD',interval:interval==='1h'?'60':interval==='15m'?'15':'5',timezone:'Etc/UTC',theme:light?'light':'dark',style:'1',locale:'zh_TW',allow_symbol_change:false,hide_side_toolbar:false,withdateranges:true,save_image:false,support_host:'https://www.tradingview.com'});
    script.onerror=()=>{if(active){window.clearTimeout(timeout);setStatus('failed');}};
    container.append(script);
    return()=>{active=false;window.clearTimeout(timeout);observer.disconnect();script.onerror=null;target.replaceChildren();};
  },[light,attempt,brokerChart,barsPending,interval]);
  const quote=market?.quote;
  return <section className="live-market" aria-label="即時看盤">
    <div className="instrument-header"><div><h1>XAU / USD <span>即時參考行情</span></h1><div className="market-subtitle">{brokerChart?'cTrader DEMO · Bid K 線 · UTC':'TradingView · OANDA:XAUUSD · UTC'}</div></div><span className="fine">{brokerChart?'券商 DEMO 盤面':'外部參考圖'}</span></div>
    <div className="live-status" role="status">{brokerChart?<><span>{forming?'最後一根隨 tick 更新':'等待最新 tick；目前顯示已收棒'}</span><div className="segments" aria-label="即時 K 線週期">{(['5m','15m','1h'] as const).map(value=><button key={value} className={interval===value?'active':''} aria-pressed={interval===value} onClick={()=>setInterval(value)}>{value==='1h'?'1 小時':value==='5m'?'5 分':'15 分'}</button>)}</div></>:barsPending?'正在讀取券商 K 線…':status==='failed'?'圖表未能載入。請檢查網路或瀏覽器阻擋設定。':import.meta.env.MODE==='pages'?'TradingView · OANDA 外部參考圖':'cTrader K 線尚未取得；顯示 TradingView 外部參考圖。'}{status==='failed'&&!brokerChart&&<button onClick={()=>setAttempt(n=>n+1)}>重新載入圖表</button>}</div>
    {import.meta.env.MODE!=='pages'&&<div className="demo-quote" role="status"><strong>{quote?.status==='CURRENT'?'cTrader DEMO · 最新 tick':quote?.status==='STALE'?'cTrader DEMO · 報價已過期':'cTrader DEMO · 報價未連線'}</strong>{quote?.bid&&quote.ask?<><span>賣出 BID <b>{quote.bid}</b></span><span>買進 ASK <b>{quote.ask}</b></span><small>{quote.source_time_utc??'來源時間未提供'} · {quote.age_seconds===null?'時間未確認':`${Math.round(quote.age_seconds)} 秒前`}</small></>:<small>{market?.connection_status??'正在讀取'}</small>}</div>}
    {brokerChart&&<div className="forming-strip" aria-label="形成中 K 棒數據">{forming?<><strong>形成中 · {new Date(forming.bar.time*1000).toISOString().slice(11,16)} UTC</strong><span>{forming.price_basis==='observed_bid_ticks'?'觀測開':'開'} {forming.bar.open.toFixed(2)}</span><span>{forming.price_basis==='observed_bid_ticks'?'觀測高':'高'} {forming.bar.high.toFixed(2)}</span><span>{forming.price_basis==='observed_bid_ticks'?'觀測低':'低'} {forming.bar.low.toFixed(2)}</span><span key={forming.bar.close} className={forming.bar.close>=forming.bar.open?'positive tick-change':'negative tick-change'}>收 {forming.bar.close.toFixed(2)}</span><span>接收 tick {forming.bar.volume.toLocaleString()}</span><small>{forming.partial?'本棒從連線中途觀測；開高低與量可能不完整':'量為本機接收的 Bid 更新筆數'}</small></>:<span>尚無有效形成中棒；不以過期價格補動畫。</span>}</div>}
    {provisional>0&&<p className="fine forming-provisional">最近 {provisional} 根已結束棒仍為本機觀測值（量可能不完整），等待券商原生收棒取代。</p>}
    <div className="live-chart">{brokerChart?<LiveCandleChart bars={displayBars} light={light} interval={interval}/>:barsPending?<div className="chart-loading">正在讀取 cTrader DEMO 行情…</div>:<div className="tradingview-host" ref={host}/>}</div>
    {!brokerChart&&<div className="live-attribution"><a href="https://www.tradingview.com/symbols/XAUUSD/?exchange=OANDA" target="_blank" rel="noopener noreferrer">XAUUSD 圖表</a><span>{import.meta.env.MODE==='pages'?'由 TradingView 提供；與合成回放行情來源不同':'由 TradingView 提供；與 cTrader DEMO 報價來源不同'}</span></div>}
    <div className="limitations"><p>{import.meta.env.MODE==='pages'?'TradingView 的更新時間依資料供應商；請以圖表上的來源與時間為準。':'實體與影線隨實際 Bid 更新；均線含形成中棒。歷史量為券商 tick 量，形成中量為本機接收數，並非全球成交量。'}</p><p>{import.meta.env.MODE==='pages'?'TradingView 外部圖不進入公開合成回放的案例排名。':'形成中棒只供繪圖，案例檢索仍只用已收 K 線；斷線不補量、不模擬價格。'}</p></div>
  </section>;
}
