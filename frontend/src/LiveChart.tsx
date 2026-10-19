import {useEffect,useRef,useState} from 'react';
import {api} from './api';
import Chart from './Chart';
import type {DemoBars,DemoMarket} from './demoMarket';

export default function LiveChart({light,market}:{light:boolean;market:DemoMarket|null}) {
  const host=useRef<HTMLDivElement>(null);
  const [status,setStatus]=useState<'loading'|'embedded'|'failed'>('loading');
  const [attempt,setAttempt]=useState(0);
  const [interval,setInterval]=useState<'5m'|'15m'|'1h'>('5m');
  const [brokerBars,setBrokerBars]=useState<DemoBars|null>(null);
  const [barsPending,setBarsPending]=useState(import.meta.env.MODE!=='pages');
  useEffect(()=>{
    if(import.meta.env.MODE==='pages')return;
    let active=true;let timer:number|undefined;
    const refresh=async()=>{
      try{const value=await api<DemoBars>(`/broker/bars?interval=${interval}`);if(active)setBrokerBars(value);}
      catch{if(active)setBrokerBars(null);}
      if(active){setBarsPending(false);timer=window.setTimeout(refresh,15000);}
    };
    setBrokerBars(null);setBarsPending(true);void refresh();
    return()=>{active=false;if(timer)window.clearTimeout(timer);};
  },[interval]);
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
    <div className="instrument-header"><div><h1>XAU / USD <span>即時參考行情</span></h1><div className="market-subtitle">{brokerChart?'cTrader DEMO · 已收 K 線 · UTC':'TradingView · OANDA:XAUUSD · UTC'}</div></div><span className="fine">{brokerChart?'券商 DEMO 盤面':'外部參考圖'}</span></div>
    <div className="live-status" role="status">{brokerChart?<><span>cTrader DEMO 三週期已收盤 K 線</span><div className="segments" aria-label="即時 K 線週期">{(['5m','15m','1h'] as const).map(value=><button key={value} className={interval===value?'active':''} aria-pressed={interval===value} onClick={()=>setInterval(value)}>{value==='1h'?'1 小時':value==='5m'?'5 分':'15 分'}</button>)}</div></>:barsPending?'正在讀取券商 K 線…':status==='failed'?'圖表未能載入。請檢查網路或瀏覽器阻擋設定。':import.meta.env.MODE==='pages'?'TradingView · OANDA 外部參考圖':'cTrader K 線尚未取得；顯示 TradingView 外部參考圖。'}{status==='failed'&&!brokerChart&&<button onClick={()=>setAttempt(n=>n+1)}>重新載入圖表</button>}</div>
    {import.meta.env.MODE!=='pages'&&<div className="demo-quote" role="status"><strong>{quote?.status==='CURRENT'?'cTrader DEMO · 最新 tick':quote?.status==='STALE'?'cTrader DEMO · 報價已過期':'cTrader DEMO · 報價未連線'}</strong>{quote?.bid&&quote.ask?<><span>賣出 BID <b>{quote.bid}</b></span><span>買進 ASK <b>{quote.ask}</b></span><small>{quote.source_time_utc??'來源時間未提供'} · {quote.age_seconds===null?'時間未確認':`${Math.round(quote.age_seconds)} 秒前`}</small></>:<small>{market?.connection_status??'正在讀取'}</small>}</div>}
    <div className="live-chart">{brokerChart?<Chart bars={brokerBars!.bars} light={light} ariaLabel="cTrader DEMO 黃金已收 K 線，UTC 時間"/>:barsPending?<div className="chart-loading">正在讀取 cTrader DEMO 行情…</div>:<div className="tradingview-host" ref={host}/>}</div>
    {!brokerChart&&<div className="live-attribution"><a href="https://www.tradingview.com/symbols/XAUUSD/?exchange=OANDA" target="_blank" rel="noopener noreferrer">XAUUSD 圖表</a><span>由 TradingView 提供；與 cTrader DEMO 報價來源不同</span></div>}
    <div className="limitations"><p>價格依來源時間判斷新舊；休市可能只有收盤前最後一次 tick。</p><p>{import.meta.env.MODE==='pages'?'TradingView 外部圖不進入公開合成回放的案例排名。':'DEMO 已收 K 線供即時案例查詢；DEMO 委託須在右側草稿中由你確認。'}</p></div>
  </section>;
}
