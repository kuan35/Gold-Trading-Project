import type {Candle,ComparisonCharts} from './caseComparisonData';
import type {Marker} from './types';

type Execution=ComparisonCharts['cases'][number]['execution'];
type Gap={from:number;to:number;missingSlots:number};
export type LogicalWindow={from:number;to:number};
const priceKeys=['open','high','low','close'] as const;

/** Display-only merge of frozen reference segments. Never synthesizes OHLC. */
export function executionDisplay(before:Candle[],execution?:Execution):{bars:Candle[];markers:Marker[];gaps:Gap[];reason:string}{
 const empty=(reason:string)=>({bars:[] as Candle[],markers:[] as Marker[],gaps:[] as Gap[],reason});
 if(execution?.status!=='AVAILABLE'||!execution.bars.length)return empty(execution?.reason??'原單參考進出場資料尚未建立。');
 const byTime=new Map<number,Candle>();
 for(const segment of [before,execution.bars,execution.close_bars]){
  let previous=-Infinity;
  for(const b of segment){
   if(!Number.isInteger(b.time)||b.time%300!==0||b.time<=previous||priceKeys.some(k=>!Number.isFinite(b[k])||b[k]<=0)||b.low>Math.min(b.open,b.close)||b.high<Math.max(b.open,b.close))return empty('參考K棒時間或價格不合法，未合併原單圖。');
   previous=b.time;
   const old=byTime.get(b.time);
   if(old&&priceKeys.some(k=>old[k]!==b[k]))return empty('相同時間的參考K棒價格有衝突，未合併原單圖。');
   byTime.set(b.time,b);
  }
 }
 const bars=[...byTime.values()].sort((a,b)=>a.time-b.time),gaps:Gap[]=[];
 const markers=execution.markers.filter(m=>byTime.has(m.time));
 for(let i=1;i<bars.length;i++){
  const from=bars[i-1].time,to=bars[i].time;
  if(to-from>300){
   gaps.push({from,to,missingSlots:(to-from)/300-1});
   markers.push({id:'reference-gap-'+to,time:to,position:'aboveBar',color:'#e6bb76',shape:'circle',text:'時間間隔'});
  }
 }
 return {bars,markers:markers.sort((a,b)=>a.time-b.time),gaps,reason:''};
}

/** Inclusive source indexes for a known execution's contiguous neighbourhood; no padding. */
export function executionFocusRange(bars:Candle[],markers:Marker[],action:'ENTRY'|'CLOSE'):LogicalWindow|null{
 const target=markers.find(m=>m.action===action),index=target?bars.findIndex(b=>b.time===target.time):-1;
 if(index<0)return null;
 let start=index,end=index;
 while(start>0&&bars[start].time-bars[start-1].time===300)start--;
 while(end<bars.length-1&&bars[end+1].time-bars[end].time===300)end++;
 return {from:Math.max(start,index-12),to:Math.min(end,index+6)};
}
