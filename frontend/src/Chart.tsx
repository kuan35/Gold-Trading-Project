import {chartTheme} from './chartTheme';
import {useEffect,useRef} from 'react';
import {CandlestickSeries,ColorType,createChart,createSeriesMarkers,HistogramSeries,LineSeries,type UTCTimestamp} from 'lightweight-charts';
import type {Bar,Marker} from './types';
import {displayMarker} from './chartMarkers';
const EMPTY_MARKERS:Marker[]=[];const EMPTY_IDS:string[]=[];
type Props = {bars:Array<Omit<Bar,'volume'>&{volume?:number}>;markers?:Marker[];light:boolean;averages?:boolean;showVolume?:boolean;focusIds?:string[];ariaLabel?:string;paddingBars?:number};
export default function Chart({bars,markers=EMPTY_MARKERS,light,averages=true,showVolume=true,focusIds=EMPTY_IDS,paddingBars=10,ariaLabel='黃金 K 線與操作標記，時間依回放行情來源顯示'}:Props) {
  const host = useRef<HTMLDivElement>(null);
  useEffect(()=>{
    if(!host.current) return;
    const palette=chartTheme(light),{background,text,grid}=palette;
    const chart=createChart(host.current,{autoSize:true,layout:{background:{type:ColorType.Solid,color:background},textColor:text,fontFamily:'Segoe UI, Microsoft JhengHei, sans-serif',fontSize:11,attributionLogo:true},grid:{vertLines:{color:grid},horzLines:{color:grid}},rightPriceScale:{borderColor:grid},timeScale:{borderColor:grid,timeVisible:true,secondsVisible:false},crosshair:{vertLine:{labelBackgroundColor:palette.crosshair},horzLine:{labelBackgroundColor:palette.crosshair}}});
    const candles=chart.addSeries(CandlestickSeries,{upColor:palette.up,downColor:palette.down,borderUpColor:palette.up,borderDownColor:palette.down,wickUpColor:palette.up,wickDownColor:palette.down,priceFormat:{type:'price',precision:2,minMove:0.01}});
    candles.setData(bars.map(b=>({...b,time:b.time as UTCTimestamp})));
    if(showVolume){const volume=chart.addSeries(HistogramSeries,{priceFormat:{type:'volume'},priceScaleId:'',priceLineVisible:false,lastValueVisible:false});
    volume.priceScale().applyOptions({scaleMargins:{top:0.82,bottom:0}});
    candles.priceScale().applyOptions({scaleMargins:{top:0.08,bottom:0.22}});
    volume.setData(bars.filter(b=>b.volume!==undefined).map(b=>({time:b.time as UTCTimestamp,value:b.volume!,color:b.close>=b.open?palette.volumeUp:palette.volumeDown})));}
    const plotted=markers.map(m=>displayMarker(m,focusIds));
    createSeriesMarkers(candles,plotted,{autoScale:true});
    for(const m of markers.filter(m=>m.price&&focusIds.includes(m.id||''))){
      candles.createPriceLine({price:Number(m.price),color:m.color,lineWidth:1,lineStyle:2,axisLabelVisible:true,
        title:m.action==='CLOSE'?'出場':'進場'});
    }
    if(averages) for(const [period,color] of [[20,palette.ma20],[60,palette.ma60]] as const) {
      const line=chart.addSeries(LineSeries,{color,lineWidth:1,priceLineVisible:false,lastValueVisible:false,crosshairMarkerVisible:false});
      line.setData(bars.flatMap((b,index)=>index<period-1?[]:[{time:b.time as UTCTimestamp,value:bars.slice(index-period+1,index+1).reduce((sum,c)=>sum+c.close,0)/period}]));
    }
    const fitBars=()=>{
      if(!host.current?.clientWidth||!host.current.clientHeight)return;
      chart.timeScale().fitContent();
      // Leave room after the last candle for arrows and their execution labels.
      if(bars.length)chart.timeScale().setVisibleLogicalRange({from:0,to:bars.length+paddingBars});
    };
    const resize=new ResizeObserver(fitBars);
    resize.observe(host.current);
    fitBars();
    return ()=>{resize.disconnect();chart.remove();};
  },[bars,markers,light,averages,focusIds,showVolume,paddingBars]);
  return <div ref={host} className="chart-canvas" role="img" aria-label={ariaLabel}/>;
}
