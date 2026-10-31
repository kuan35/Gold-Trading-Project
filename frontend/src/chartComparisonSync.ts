// Synchronize by candle offset from the reference, never by unrelated dates/prices.
import {useEffect,useId,useRef} from 'react';
import type {ChartRuntime} from './ChartWorkspaceTools';import type {Candle} from './chartWorkspaceModel';import type {UTCTimestamp} from 'lightweight-charts';
type Message={group:string;sender:string;from?:number;to?:number;offset?:number|null};
const listeners=new Set<(message:Message)=>void>();
export function relativeRange(range:{from:number;to:number},anchor:number){return {from:range.from-anchor,to:range.to-anchor};}
export function useComparisonSync(runtime:ChartRuntime|null,bars:Candle[],group?:string,anchor=bars.length-1){
 const id=useId(),applying=useRef(false);
 useEffect(()=>{if(!runtime||runtime.active===false||!group)return;const {chart,candles}=runtime;
  const receive=(m:Message)=>{if(m.group!==group||m.sender===id)return;applying.current=true;
   try{if(m.from!==undefined&&m.to!==undefined){const current=chart.timeScale().getVisibleLogicalRange(),from=m.from+anchor,to=m.to+anchor;if(!current||Math.abs(current.from-from)>.01||Math.abs(current.to-to)>.01)chart.timeScale().setVisibleLogicalRange({from,to});}
    if(m.offset!==undefined){const b=m.offset===null?undefined:bars[anchor+m.offset];if(b)chart.setCrosshairPosition(b.close,b.time as UTCTimestamp,candles);else chart.clearCrosshairPosition();}
   }finally{applying.current=false;}
  };
  const range=(r:{from:number;to:number}|null)=>{if(r&&!applying.current)listeners.forEach(fn=>fn({group,sender:id,...relativeRange(r,anchor)}));};
  const cross=(p:{time?:unknown})=>{if(applying.current)return;const i=bars.findIndex(b=>b.time===p.time);listeners.forEach(fn=>fn({group,sender:id,offset:i>=0?i-anchor:null}));};
  listeners.add(receive);chart.timeScale().subscribeVisibleLogicalRangeChange(range);chart.subscribeCrosshairMove(cross);
  return()=>{listeners.delete(receive);if(runtime.active!==false){chart.timeScale().unsubscribeVisibleLogicalRangeChange(range);chart.unsubscribeCrosshairMove(cross);}};
 },[runtime,group,anchor,bars,id]);
}
