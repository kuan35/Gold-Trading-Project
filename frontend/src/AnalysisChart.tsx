import {useEffect,useRef} from 'react';
import {createChart,CandlestickSeries,LineSeries,ColorType,createSeriesMarkers,type UTCTimestamp,type Logical} from 'lightweight-charts';
import {layerCoordinate} from './analysisChartCoordinates';
import type {Bar} from './types';
export type Layer={id:string;kind:'line'|'region'|'marker';label:string;price?:string;time?:number;start_time?:number;end_time?:number;high?:string;low?:string};
export type AnalysisFrame={bars:Omit<Bar,'volume'>[];layers:Layer[];quality:unknown};
export default function AnalysisChart({frame,light,ariaLabel,focus}:{frame:AnalysisFrame;light:boolean;ariaLabel:string;focus?:string}){
 const host=useRef<HTMLDivElement>(null),overlay=useRef<SVGSVGElement>(null);
 useEffect(()=>{if(!host.current||!frame.bars.length)return;
  const ink=light?'#24394a':'#b7c7d5',line=light?'#c9d5dd':'#243b4c';
  const chart=createChart(host.current,{autoSize:true,layout:{background:{type:ColorType.Solid,color:light?'#ffffff':'#0d1b2a'},textColor:ink},grid:{vertLines:{color:line},horzLines:{color:line}},timeScale:{timeVisible:true,secondsVisible:false},rightPriceScale:{borderColor:line}});
  const candles=chart.addSeries(CandlestickSeries,{upColor:'#64d6a4',downColor:'#ed8589',borderVisible:false,wickUpColor:'#64d6a4',wickDownColor:'#ed8589'});
  candles.setData(frame.bars.map(b=>({...b,time:b.time as UTCTimestamp})));
  for(const [period,color] of [[20,'#efbd69'],[60,'#8eafcb']] as const){const s=chart.addSeries(LineSeries,{color,lineWidth:1,lastValueVisible:false,priceLineVisible:false});s.setData(frame.bars.flatMap((b,i)=>i<period-1?[]:[{time:b.time as UTCTimestamp,value:frame.bars.slice(i-period+1,i+1).reduce((n,v)=>n+v.close,0)/period}]));}
  for(const l of frame.layers.filter(l=>l.kind==='line'&&l.price!==undefined)){const price=Number(l.price);if(Number.isFinite(price))candles.createPriceLine({price,color:l.id===focus?(light?'#1b344a':'#f8f9fc'):l.id.startsWith('draft.')?'#b1a4e3':l.id.includes('support')?'#64d6a4':'#efbd69',lineWidth:l.id===focus?2:1,lineStyle:2,axisLabelVisible:true,title:l.label});}
  createSeriesMarkers(candles,frame.layers.filter(l=>l.kind==='marker'&&l.time&&frame.bars.some(b=>b.time===l.time)).map(l=>({time:l.time as UTCTimestamp,position:'aboveBar' as const,color:'#efbd69',shape:'circle' as const,text:l.label})).sort((a,b)=>a.time-b.time));
  const paint=()=>{const svg=overlay.current;if(!svg)return;svg.replaceChildren();for(const l of frame.layers.filter(l=>l.kind==='region')){
   const coordinate=(time:number|undefined)=>layerCoordinate(time,frame.bars,n=>chart.timeScale().timeToCoordinate(n as UTCTimestamp),n=>chart.timeScale().logicalToCoordinate(n as Logical));
   const start=coordinate(l.start_time),end=coordinate(l.end_time),top=candles.priceToCoordinate(Number(l.high)),bottom=candles.priceToCoordinate(Number(l.low));
   if(start===null||end===null||top===null||bottom===null)continue;const rect=document.createElementNS('http://www.w3.org/2000/svg','rect');rect.setAttribute('x',String(Math.min(start,end)));rect.setAttribute('y',String(Math.min(top,bottom)));rect.setAttribute('width',String(Math.max(2,Math.abs(end-start))));rect.setAttribute('height',String(Math.max(2,Math.abs(bottom-top))));rect.setAttribute('fill',l.id===focus?'#efbd6930':l.id.includes('recent')?'#64d6a414':'#efbd6915');rect.setAttribute('stroke',l.id===focus?(light?'#1b344a':'#f8f9fc'):l.id.includes('recent')?'#64d6a4':'#efbd69');rect.setAttribute('stroke-width',l.id===focus?'2':'1');rect.setAttribute('stroke-dasharray','4 4');svg.append(rect);
  }};
  chart.timeScale().fitContent();chart.timeScale().subscribeVisibleLogicalRangeChange(paint);const ro=new ResizeObserver(()=>requestAnimationFrame(paint));ro.observe(host.current);const raf=requestAnimationFrame(paint);
  return()=>{cancelAnimationFrame(raf);ro.disconnect();chart.remove();};
 },[frame,light,focus]);
 return <div className="cw-chart-wrap"><div ref={host} className="cw-analysis-canvas" role="img" aria-label={ariaLabel}/><svg ref={overlay} className="cw-chart-overlay" aria-hidden="true"/></div>;
}
