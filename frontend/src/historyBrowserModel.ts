import type {Bar} from './types';
export type HistoryZone='Taiwan'|'UTC';
export function historyDateInput(time:number,zone:HistoryZone){return new Date((time+(zone==='Taiwan'?28800:0))*1000).toISOString().slice(0,16);}
export function historyTimestamp(value:string,zone:HistoryZone){
 const m=/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})$/.exec(value);if(!m)return null;
 const [year,month,day,hour,minute]=m.slice(1).map(Number),date=new Date(Date.UTC(year,month-1,day,hour,minute));
 if(date.getUTCFullYear()!==year||date.getUTCMonth()!==month-1||date.getUTCDate()!==day||date.getUTCHours()!==hour||date.getUTCMinutes()!==minute)return null;
 return date.getTime()/1000-(zone==='Taiwan'?28800:0);
}
export function mergeHistoryBars(old:Bar[],incoming:Bar[],direction:'before'|'after',limit=2400){
 const byTime=new Map([...old,...incoming].map(b=>[b.time,b]));const sorted=[...byTime.values()].sort((a,b)=>a.time-b.time);
 return direction==='before'?sorted.slice(0,limit):sorted.slice(-limit);
}

export function historyGaps(bars:Bar[],interval:string){const span=interval==='1h'?3600:interval==='15m'?900:300;return bars.slice(1).flatMap((b,i)=>b.time-bars[i].time>span?[{from_time:bars[i].time+span,to_time:b.time,seconds:b.time-bars[i].time-span}]:[]);}
