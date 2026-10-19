import {useEffect,useRef,useState} from 'react';

/** Public Pages has no access to the local cTrader account or its credentials. */
export default function PublicTicker(){
  const host=useRef<HTMLSpanElement>(null);
  const [failed,setFailed]=useState(false);
  useEffect(()=>{
    const target=host.current;
    if(!target)return;
    const widget=document.createElement('tv-ticker-tape');
    widget.setAttribute('symbols','OANDA:XAUUSD');
    widget.setAttribute('direction','horizontal');
    widget.setAttribute('item-size','compact');
    widget.setAttribute('hide-chart','');
    widget.textContent='外部行情載入中…';
    target.replaceChildren(widget);
    const script=document.createElement('script');
    script.type='module';
    script.src='https://widgets.tradingview-widget.com/w/en/tv-ticker-tape.js';
    script.onerror=()=>setFailed(true);
    document.head.append(script);
    return()=>{script.remove();target.replaceChildren();};
  },[]);
  return <div className="public-ticker"><strong>黃金參考價</strong><span ref={host} className="public-ticker-widget"/>
    <small>{failed?'外部行情暫不可用':'TradingView · OANDA:XAUUSD · 更新依資料供應商'}</small></div>;
}
