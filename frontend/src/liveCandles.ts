import type {Bar} from './types';

export type FormingCandle={bar:Bar;pending_bars:Bar[];updated_at_ms:number;partial:boolean;price_basis:string;volume_basis:string};
export type LiveChartFrame={source:string;environment:'demo';status:string;interval:string;closed_only:false;bars:Bar[];forming:FormingCandle|null;forming_status:string};

export function mergeLiveBars(closed:Bar[],pending:Bar[],forming:Bar|null):Bar[]{
 const byTime=new Map<number,Bar>();
 const lastClosed=closed.at(-1)?.time??-Infinity;
 for(const bar of pending)if(bar.time>lastClosed)byTime.set(bar.time,bar);
 for(const bar of closed)byTime.set(bar.time,bar);
 if(forming&&!byTime.has(forming.time))byTime.set(forming.time,forming);
 return [...byTime.values()].sort((a,b)=>a.time-b.time);
}
export function provisionalBarCount(closed:Bar[],pending:Bar[]):number{
 const last=closed.at(-1)?.time??-Infinity;
 return pending.filter(bar=>bar.time>last).length;
}
const sameBar=(a:Bar,b:Bar)=>a.time===b.time&&a.open===b.open&&a.high===b.high&&a.low===b.low&&a.close===b.close&&a.volume===b.volume;
export function liveUpdateKind(previous:Bar[],next:Bar[]):'reset'|'update'{
 if(!previous.length||next.length<previous.length||next.length>previous.length+1)return 'reset';
 for(let i=0;i<previous.length-1;i++)if(!sameBar(previous[i],next[i]))return 'reset';
 if(next.length>previous.length&&!sameBar(previous.at(-1)!,next[previous.length-1]))return 'reset';
 return next[previous.length-1]?.time===previous.at(-1)?.time?'update':'reset';
}
export function interpolateClose(from:number,target:Bar,progress:number,reduced:boolean):Bar{
 const p=reduced?1:Math.min(1,Math.max(0,progress));
 const close=p===1?target.close:from+(target.close-from)*(1-(1-p)**3);
 return {...target,close:Math.max(target.low,Math.min(target.high,close))};
}
