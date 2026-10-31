import {useComparisonSync} from './chartComparisonSync';
import {chartTheme} from './chartTheme';
import {useEffect,useRef,useState,type ReactNode} from 'react';
import {CandlestickSeries,ColorType,createChart,createSeriesMarkers,HistogramSeries,LineSeries,type UTCTimestamp,type ISeriesMarkersPluginApi,type IPriceLine,type Time} from 'lightweight-charts';
import type {Bar,Marker} from './types';import {displayMarker} from './chartMarkers';
import ChartWorkspaceTools,{type ChartRuntime} from './ChartWorkspaceTools';
const EMPTY_MARKERS:Marker[]=[];const EMPTY_IDS:string[]=[];
type Props={bars:Array<Omit<Bar,'volume'>&{volume?:number}>;markers?:Marker[];light:boolean;averages?:boolean;showVolume?:boolean;focusIds?:string[];ariaLabel?:string;paddingBars?:number;onHoverTime?:(time:number|null)=>void;hoverLabel?:string;annotation?:ReactNode;logicalRange?:{from:number;to:number}|null;resetToken?:number;scope?:string;syncGroup?:string;syncAnchor?:number};
export default function Chart({onHoverTime,hoverLabel,annotation,logicalRange,resetToken=0,bars,markers=EMPTY_MARKERS,light,averages=true,showVolume=true,focusIds=EMPTY_IDS,paddingBars=10,syncGroup,syncAnchor,ariaLabel='黃金 K 線與操作標記，時間依回放行情來源顯示',scope}:Props){
 const host=useRef<HTMLDivElement>(null),[runtime,setRuntime]=useState<ChartRuntime|null>(null),plugin=useRef<ISeriesMarkersPluginApi<Time>|null>(null),prices=useRef<IPriceLine[]>([]),old=useRef<typeof bars>([]),fitted=useRef(false),hover=useRef(onHoverTime);
 hover.current=onHoverTime;
 useComparisonSync(runtime,bars,syncGroup,syncAnchor);
 useEffect(()=>{if(!host.current)return;const p=chartTheme(light),chart=createChart(host.current,{autoSize:true,layout:{background:{type:ColorType.Solid,color:p.background},textColor:p.text,fontFamily:'Segoe UI, Microsoft JhengHei, sans-serif',fontSize:12},grid:{vertLines:{color:p.grid},horzLines:{color:p.grid}},rightPriceScale:{borderColor:p.grid},timeScale:{borderColor:p.grid,timeVisible:true,secondsVisible:false}});
  const candles=chart.addSeries(CandlestickSeries,{upColor:p.up,downColor:p.down,borderUpColor:p.up,borderDownColor:p.down,wickUpColor:p.up,wickDownColor:p.down,priceFormat:{type:'price',precision:2,minMove:.01}});
  const volume=chart.addSeries(HistogramSeries,{priceFormat:{type:'volume'},priceScaleId:'',priceLineVisible:false,lastValueVisible:false});volume.priceScale().applyOptions({scaleMargins:{top:.84,bottom:0}});
  const lines=[p.ma20,p.ma60].map(color=>chart.addSeries(LineSeries,{color,lineWidth:1,priceLineVisible:false,lastValueVisible:false,crosshairMarkerVisible:false}));
  plugin.current=createSeriesMarkers(candles,[],{autoScale:true});prices.current=[];old.current=[];fitted.current=false;
  chart.subscribeCrosshairMove(p=>hover.current?.(typeof p.time==='number'?p.time:null));const state={chart,candles,volume,averages:lines,active:true};setRuntime(state);
  return()=>{state.active=false;setRuntime(null);plugin.current=null;chart.remove();};
 },[light]);
 useEffect(()=>{if(!runtime||runtime.active===false)return;const {chart,candles,volume}=runtime,p=chartTheme(light),range=chart.timeScale().getVisibleLogicalRange(),previous=old.current;
  candles.setData(bars.map(b=>({...b,time:b.time as UTCTimestamp})));volume!.setData(bars.filter(b=>b.volume!==undefined).map(b=>({time:b.time as UTCTimestamp,value:b.volume!,color:b.close>=b.open?p.volumeUp:p.volumeDown})));
  runtime.averages!.forEach((line,j)=>{const period=j?60:20;line.setData(bars.flatMap((b,i)=>i<period-1?[]:[{time:b.time as UTCTimestamp,value:bars.slice(i-period+1,i+1).reduce((s,b)=>s+b.close,0)/period}]));});
  candles.priceScale().applyOptions({scaleMargins:{top:annotation?.24:.08,bottom:showVolume?.22:.08}});
  if(!fitted.current&&bars.length){chart.timeScale().setVisibleLogicalRange(logicalRange??{from:0,to:bars.length+paddingBars});fitted.current=true;}
  else if(range&&previous.length){const shift=bars.findIndex(b=>b.time===previous[0].time);if(shift>=0)chart.timeScale().setVisibleLogicalRange({from:range.from+shift,to:range.to+shift});else chart.timeScale().setVisibleLogicalRange(range);}
  old.current=bars;
 },[runtime,bars,light,averages,showVolume,!!annotation]);
 useEffect(()=>{if(!runtime||runtime.active===false)return;plugin.current?.setMarkers(markers.map(m=>displayMarker(m,focusIds)));for(const line of prices.current)runtime.candles.removePriceLine(line);prices.current=[];
  for(const m of markers.filter(m=>m.price&&focusIds.includes(m.id??'')))prices.current.push(runtime.candles.createPriceLine({price:Number(m.price),color:m.color,lineWidth:1,lineStyle:2,axisLabelVisible:true,title:m.action==='CLOSE'?'出場':'進場'}));
 },[runtime,markers,focusIds]);
 useEffect(()=>{if(!runtime||runtime.active===false||!bars.length)return;runtime.chart.timeScale().setVisibleLogicalRange(logicalRange??{from:0,to:bars.length+paddingBars});},[runtime,logicalRange?.from,logicalRange?.to,resetToken]);
 const drawingScope=scope??`${ariaLabel}:${bars[0]?.time??''}:${bars.at(-1)?.time??''}`;
 return <div className="chart-frame gd-chart-workspace" data-annotated={!!annotation||undefined} style={{height:'100%',minHeight:280}}><ChartWorkspaceTools runtime={runtime} bars={bars} scope={drawingScope} defaultVolume={showVolume} defaultAverages={averages}/><div className="gd-chart-plot"><div ref={host} className="chart-canvas" role="img" aria-label={ariaLabel}/>{annotation&&<div className="chart-annotation" role="note" aria-label="歷史原單報酬">{annotation}</div>}{hoverLabel&&<output className="trade-hover-label">{hoverLabel}</output>}</div></div>;
}
