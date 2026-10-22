import {useEffect,useRef} from 'react';
import {CandlestickSeries,ColorType,createChart,HistogramSeries,LineSeries,type UTCTimestamp,type IChartApi,type ISeriesApi} from 'lightweight-charts';
import type {Bar} from './types';
import {interpolateClose,liveUpdateKind} from './liveCandles';

type Controller={chart:IChartApi;candles:ISeriesApi<'Candlestick'>;volume:ISeriesApi<'Histogram'>;lines:ISeriesApi<'Line'>[]};
const point=(b:Bar)=>({...b,time:b.time as UTCTimestamp});
const vol=(b:Bar)=>({time:b.time as UTCTimestamp,value:b.volume,color:b.close>=b.open?'#6ab5a359':'#d6848559'});
const average=(bars:Bar[],period:number)=>bars.flatMap((b,i)=>i<period-1?[]:[{time:b.time as UTCTimestamp,value:bars.slice(i-period+1,i+1).reduce((sum,p)=>sum+p.close,0)/period}]);

export default function LiveCandleChart({bars,light,interval}:{bars:Bar[];light:boolean;interval:string}){
 const host=useRef<HTMLDivElement>(null),controller=useRef<Controller|null>(null),previous=useRef<Bar[]>([]),drawn=useRef<Bar|null>(null),raf=useRef<number|undefined>(undefined);
 useEffect(()=>{
  if(!host.current)return;
  const background=light?'#ffffff':'#191e26',text=light?'#49595d':'#b4bfce',grid=light?'#e9eef0':'#2a303b';
  const chart=createChart(host.current,{autoSize:true,layout:{background:{type:ColorType.Solid,color:background},textColor:text,fontFamily:'Segoe UI, Microsoft JhengHei, sans-serif',fontSize:11,attributionLogo:true},grid:{vertLines:{color:grid},horzLines:{color:grid}},timeScale:{timeVisible:true,borderColor:grid,rightOffset:5},rightPriceScale:{borderColor:grid},crosshair:{vertLine:{labelBackgroundColor:'#42767b'},horzLine:{labelBackgroundColor:'#42767b'}}});
  const candles=chart.addSeries(CandlestickSeries,{upColor:'#6ab5a3',downColor:'#d68485',borderUpColor:'#6ab5a3',borderDownColor:'#d68485',wickUpColor:'#6ab5a3',wickDownColor:'#d68485',priceFormat:{type:'price',precision:2,minMove:0.01}});
  candles.priceScale().applyOptions({scaleMargins:{top:.08,bottom:.22}});
  const volume=chart.addSeries(HistogramSeries,{priceFormat:{type:'volume'},priceScaleId:'',priceLineVisible:false,lastValueVisible:false});
  volume.priceScale().applyOptions({scaleMargins:{top:.82,bottom:0}});
  const lines=['#dab976','#8baaca'].map(color=>chart.addSeries(LineSeries,{color,lineWidth:1,priceLineVisible:false,lastValueVisible:false,crosshairMarkerVisible:false}));
  controller.current={chart,candles,volume,lines};previous.current=[];drawn.current=null;
  return()=>{if(raf.current!==undefined)cancelAnimationFrame(raf.current);controller.current=null;chart.remove();};
 },[light,interval]);
 useEffect(()=>{
  const c=controller.current;if(!c||!bars.length)return;
  if(raf.current!==undefined)cancelAnimationFrame(raf.current);
  const old=previous.current,target=bars.at(-1)!,reset=liveUpdateKind(old,bars)==='reset';
  if(reset){
   const range=c.chart.timeScale().getVisibleLogicalRange();
   const oldIndex=old.length?bars.findIndex(b=>b.time===old[0].time):0;
   c.candles.setData(bars.map(point));c.volume.setData(bars.map(vol));
   c.lines.forEach((line,i)=>line.setData(average(bars,i===0?20:60)));
   if(!old.length)c.chart.timeScale().setVisibleLogicalRange({from:Math.max(0,bars.length-80),to:bars.length+5});
   else if(range){const shift=oldIndex>=0?oldIndex:-(old.findIndex(b=>b.time===bars[0].time));c.chart.timeScale().setVisibleLogicalRange({from:range.from+shift,to:range.to+shift});}
   drawn.current=target;
  }else{
   // Ordinary ticks update only the last point; no chart rebuild, fit or scroll.
   c.volume.update(vol(target));
   c.lines.forEach((line,i)=>{const p=average(bars,i===0?20:60).at(-1);if(p)line.update(p);});
   const start=drawn.current?.time===target.time?drawn.current.close:target.close;
   const reduced=window.matchMedia('(prefers-reduced-motion: reduce)').matches;
   const started=performance.now();
   const animate=(now:number)=>{
    const p=Math.min(1,(now-started)/160),bar=interpolateClose(start,target,p,reduced);
    c.candles.update(point(bar));drawn.current=bar;
    if(p<1&&!reduced&&!document.hidden)raf.current=requestAnimationFrame(animate);
   };
   animate(started);
  }
  previous.current=bars;
 },[bars,light,interval]);
 return <div ref={host} className="chart-canvas live-candle-canvas" role="img" aria-label={`cTrader DEMO ${interval} Bid K線與tick量，最後一根形成中`}/>;
}
