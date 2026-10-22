/** Exact candle time or its next close boundary; never invent a nearest candle. */
export function layerCoordinate(time:number|undefined,bars:{time:number}[],exact:(n:number)=>number|null,logical:(n:number)=>number|null):number|null{
 if(time===undefined||!Number.isFinite(time)||!bars.length)return null;
 const coordinate=exact(time);if(coordinate!==null)return coordinate;
 if(bars.length<2)return null;
 const last=bars[bars.length-1].time,span=last-bars[bars.length-2].time;
 return span>0&&time===last+span?logical(bars.length):null;
}
