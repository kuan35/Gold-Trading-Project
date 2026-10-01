import {useEffect,useRef,useState} from 'react';

// Hosted widget only: no credentials, price extraction or order-engine access.
export default function LiveChart({light}:{light:boolean}) {
  const host=useRef<HTMLDivElement>(null);
  const [status,setStatus]=useState<'loading'|'embedded'|'failed'>('loading');
  const [attempt,setAttempt]=useState(0);
  useEffect(()=>{
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
      if(frame&&active){
        frame.title='TradingView 黃金即時參考圖表';
        // Frame creation is observable; cross-origin feed freshness is not.
        window.clearTimeout(timeout);setStatus('embedded');observer.disconnect();
      }
    });
    observer.observe(container,{childList:true,subtree:true});
    const script=document.createElement('script');
    script.src='https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js';
    script.async=true;
    script.textContent=JSON.stringify({autosize:true,symbol:'OANDA:XAUUSD',interval:'5',timezone:'Etc/UTC',theme:light?'light':'dark',style:'1',locale:'zh_TW',allow_symbol_change:false,hide_side_toolbar:false,withdateranges:true,save_image:false,support_host:'https://www.tradingview.com'});
    script.onerror=()=>{if(active){window.clearTimeout(timeout);setStatus('failed');}};
    container.append(script);
    return ()=>{active=false;window.clearTimeout(timeout);observer.disconnect();script.onerror=null;target.replaceChildren();};
  },[light,attempt]);
  return <section className="live-market" aria-label="TradingView 即時看盤">
    <div className="instrument-header"><div><h1>XAU / USD <span>即時參考行情</span></h1><div className="market-subtitle">TradingView · OANDA:XAUUSD · UTC</div></div><span className="fine">僅供看盤</span></div>
    <div className="live-status" role="status">{status==='loading'?'正在載入 TradingView 圖表…':status==='failed'?'圖表未能載入。請檢查網路或瀏覽器阻擋設定。':'圖表已嵌入 · 報價時間與市場狀態以圖表內顯示為準。'}{status==='failed'&&<button onClick={()=>setAttempt(n=>n+1)}>重新載入圖表</button>}</div>
    <div className="live-chart" ref={host}/>
    <div className="live-attribution"><a href="https://www.tradingview.com/symbols/XAUUSD/?exchange=OANDA" target="_blank" rel="noopener noreferrer">XAUUSD 圖表</a><span>由 TradingView 提供</span></div>
    <div className="limitations"><p>開市且來源正常時行情自動更新；休市、延遲或斷線狀態請依圖表顯示判讀。</p><p>此圖表的價格與指標尚未接入模擬成交、案例檢索或對話助手。</p></div>
  </section>;
}
