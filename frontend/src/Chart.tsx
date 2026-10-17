import {useEffect,useRef} from 'react';
import {CandlestickSeries,ColorType,createChart,createSeriesMarkers,HistogramSeries,LineSeries,type UTCTimestamp} from 'lightweight-charts';
import type {Bar,Marker} from './types';
import {displayMarker} from './chartMarkers';
type Props = {bars:Bar[];markers?:Marker[];light:boolean;averages?:boolean;focusIds?:string[]};
export default function Chart({bars,markers=[],light,averages=true,focusIds=[]}:Props) {
  const host = useRef<HTMLDivElement>(null);
  useEffect(()=>{
    if(!host.current) return;
    const background = light?'#ffffff':'#191e26', text = light?'#49595d':'#b4bfce',grid=light?'#e9eef0':'#2a303b';
    const chart=createChart(host.current,{autoSize:true,layout:{background:{type:ColorType.Solid,color:background},textColor:text,fontFamily:'Segoe UI, Microsoft JhengHei, sans-serif',fontSize:11,attributionLogo:true},grid:{vertLines:{color:grid},horzLines:{color:grid}},rightPriceScale:{borderColor:grid},timeScale:{borderColor:grid,timeVisible:true,secondsVisible:false},crosshair:{vertLine:{labelBackgroundColor:'#42767b'},horzLine:{labelBackgroundColor:'#42767b'}}});
    const candles=chart.addSeries(CandlestickSeries,{upColor:'#6ab5a3',downColor:'#d68485',borderUpColor:'#6ab5a3',borderDownColor:'#d68485',wickUpColor:'#6ab5a3',wickDownColor:'#d68485',priceFormat:{type:'price',precision:2,minMove:0.01}});
    candles.setData(bars.map(b=>({...b,time:b.time as UTCTimestamp})));
    const volume=chart.addSeries(HistogramSeries,{priceFormat:{type:'volume'},priceScaleId:'',priceLineVisible:false,lastValueVisible:false});
    volume.priceScale().applyOptions({scaleMargins:{top:0.82,bottom:0}});
    candles.priceScale().applyOptions({scaleMargins:{top:0.08,bottom:0.22}});
    volume.setData(bars.map(b=>({time:b.time as UTCTimestamp,value:b.volume,color:b.close>=b.open?'#6ab5a340':'#d6848540'})));
    const plotted=markers.map(m=>displayMarker(m,focusIds));
    createSeriesMarkers(candles,plotted,{autoScale:true});
    for(const m of markers.filter(m=>m.price&&focusIds.includes(m.id||''))){
      candles.createPriceLine({price:Number(m.price),color:m.color,lineWidth:1,lineStyle:2,axisLabelVisible:true,
        title:m.action==='CLOSE'?'出場':'進場'});
    }
    if(averages) for(const [period,color] of [[20,'#dab976'],[60,'#8baaca']] as const) {
      const line=chart.addSeries(LineSeries,{color,lineWidth:1,priceLineVisible:false,lastValueVisible:false,crosshairMarkerVisible:false});
      line.setData(bars.flatMap((b,index)=>index<period-1?[]:[{time:b.time as UTCTimestamp,value:bars.slice(index-period+1,index+1).reduce((sum,c)=>sum+c.close,0)/period}]));
    }
    const fitBars=()=>{
      if(!host.current?.clientWidth||!host.current.clientHeight)return;
      chart.timeScale().fitContent();
      // Leave room after the last candle for arrows and their execution labels.
      if(bars.length)chart.timeScale().setVisibleLogicalRange({from:0,to:bars.length+10});
    };
    const resize=new ResizeObserver(fitBars);
    resize.observe(host.current);
    fitBars();
    return ()=>{resize.disconnect();chart.remove();};
  },[bars,markers,light,averages,focusIds]);
  return <div ref={host} className="chart-canvas" role="img" aria-label="黃金 K 線與操作標記，時間依回放行情來源顯示"/>;
}
