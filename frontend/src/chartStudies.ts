import {LineSeries,HistogramSeries,type IChartApi,type ISeriesApi,type UTCTimestamp} from 'lightweight-charts';
import {studyValues,studies,type Study,type Candle} from './chartWorkspaceModel';
export type StudyChart=Pick<IChartApi,'addSeries'|'removeSeries'|'panes'>;
type Point={time:UTCTimestamp;value:number;color?:string};
type Entry={series:ISeriesApi<'Line'|'Histogram'>;study?:Study;points:Point[]|null};
const colors=['#d6af68','#8daece','#dc9e68','#b6a2d9','#78b5ac','#be8da1','#95ba80','#d6af68','#8daece','#c19970'];
const same=(a:Point,b:Point)=>a.time===b.time&&a.value===b.value&&a.color===b.color;

// Series and pane ownership follow the user's study selection, never tick cadence.
export class ChartStudyLayer{
 private entries:Entry[]=[];private signature='';
 constructor(private chart:StudyChart,private nativeVolume:boolean){}
 update(selected:Study[],bars:Candle[],volume:boolean){
  const ordered=studies.filter(s=>selected.includes(s));
  const extraVolume=!this.nativeVolume&&volume;
  const signature=ordered.join('|')+':'+extraVolume;
  if(signature!==this.signature){
   this.dispose();this.signature=signature;
   const paneKinds=['RSI14','MACD','ATR14'].filter(kind=>ordered.some(s=>s.startsWith(kind)));
   for(const study of ordered){
    const kind=study.startsWith('MACD')?'MACD':study,pane=paneKinds.includes(kind)?paneKinds.indexOf(kind)+1:0;
    const series=this.chart.addSeries(LineSeries,{color:colors[studies.indexOf(study)],lineWidth:1,lastValueVisible:false,priceLineVisible:false,title:study},pane);
    this.entries.push({series,study,points:null});
   }
   if(extraVolume){
    const series=this.chart.addSeries(HistogramSeries,{priceFormat:{type:'volume'},priceScaleId:'',lastValueVisible:false,priceLineVisible:false});
    series.priceScale().applyOptions({scaleMargins:{top:.84,bottom:0}});this.entries.push({series,points:null});
   }
   // Relative sizes initialize new study panes once. Subsequent ticks preserve divider drags.
   if(paneKinds.length)this.chart.panes().forEach((pane,i)=>pane.setStretchFactor(i===0?3:1));
  }
  for(const entry of this.entries){
   const points:Point[]=entry.study?studyValues(entry.study,bars).map(p=>({...p,time:p.time as UTCTimestamp})):
    bars.filter(b=>b.volume!==undefined).map(b=>({time:b.time as UTCTimestamp,value:b.volume!,color:b.close>=b.open?'#59d8a745':'#f58c9345'}));
   const old=entry.points;
   if(old&&old.length===points.length&&old.every((p,i)=>same(p,points[i])))continue;
   const replaceTail=old&&old.length>0&&old.length===points.length&&old.at(-1)!.time===points.at(-1)!.time&&old.slice(0,-1).every((p,i)=>same(p,points[i]));
   const append=old&&old.length>0&&points.length===old.length+1&&old.every((p,i)=>same(p,points[i]));
   if(replaceTail||append)entry.series.update(points.at(-1)!);
   else entry.series.setData(points); // warmup, backfill, corrected history or a new time window
   entry.points=points;
  }
 }
 dispose(){for(const {series} of this.entries)this.chart.removeSeries(series);this.entries=[];this.signature='';}
}
