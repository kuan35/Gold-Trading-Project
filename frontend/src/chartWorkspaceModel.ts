export type Candle={time:number;open:number;high:number;low:number;close:number;volume?:number};
export const studies=['SMA20','SMA60','EMA20','EMA60','BBupper','BBlower','RSI14','MACD','MACDsignal','ATR14'] as const;
export type Study=typeof studies[number];
type Point={time:number;value:number};
const ema=(values:number[],period:number):Array<number|undefined>=>{
 const out:Array<number|undefined>=Array(values.length).fill(undefined);if(values.length<period)return out;
 out[period-1]=values.slice(0,period).reduce((s,n)=>s+n,0)/period;
 for(let i=period;i<values.length;i++)out[i]=values[i]*2/(period+1)+out[i-1]!*(1-2/(period+1));return out;
};
export function studyValues(study:Study,bars:Candle[]):Point[]{
 const closes=bars.map(b=>b.close),out:Point[]=[];const period=study.endsWith('60')?60:20;
 if(study.startsWith('EMA'))return ema(closes,period).flatMap((value,i)=>value===undefined?[]:[{time:bars[i].time,value}]);
 if(study==='MACD'||study==='MACDsignal'){
  const fast=ema(closes,12),slow=ema(closes,26);const macd=slow.flatMap((n,i)=>n===undefined?[]:[{time:bars[i].time,value:fast[i]!-n}]);
  return study==='MACD'?macd:ema(macd.map(p=>p.value),9).flatMap((value,i)=>value===undefined?[]:[{time:macd[i].time,value}]);
 }
 if(study==='ATR14'||study==='RSI14'){
  let avg=0,gain=0,loss=0;
  for(let i=1;i<bars.length;i++){
   const change=closes[i]-closes[i-1],tr=Math.max(bars[i].high-bars[i].low,Math.abs(bars[i].high-closes[i-1]),Math.abs(bars[i].low-closes[i-1]));
   if(i<=14){avg+=tr/14;gain+=Math.max(0,change)/14;loss+=Math.max(0,-change)/14;}
   else{avg=(avg*13+tr)/14;gain=(gain*13+Math.max(0,change))/14;loss=(loss*13+Math.max(0,-change))/14;}
   if(i>=14)out.push({time:bars[i].time,value:study==='ATR14'?avg:loss===0?(gain===0?50:100):100-100/(1+gain/loss)});
  }return out;
 }
 for(let i=period-1;i<bars.length;i++){
  const values=closes.slice(i-period+1,i+1),mean=values.reduce((s,n)=>s+n,0)/period,sd=Math.sqrt(values.reduce((s,n)=>s+(n-mean)**2,0)/period);
  out.push({time:bars[i].time,value:mean+(study==='BBupper'?2*sd:study==='BBlower'?-2*sd:0)});
 }return out;
}
export type Drawing={id:string;kind:'horizontal'|'trend'|'ray'|'rectangle'|'text'|'measure';points:{time:number;price:number}[];text:string};
export function decodeDrawings(raw:string|null,scope:string):Drawing[]{
 try{const v=JSON.parse(raw??'null');if(v?.scope!==scope||!Array.isArray(v.drawings))return [];
  return v.drawings.slice(0,100).filter((d:Drawing)=>typeof d.id==='string'&&['horizontal','trend','ray','rectangle','text','measure'].includes(d.kind)&&Array.isArray(d.points)&&d.points.length===(['horizontal','text'].includes(d.kind)?1:2)&&d.points.every(p=>Number.isFinite(p.time)&&Number.isFinite(p.price)&&p.price>0)&&typeof d.text==='string'&&d.text.length<=100);
 }catch{return [];}
}
export class DrawingHistory{
 private past:Drawing[][]=[];private future:Drawing[][]=[];current:Drawing[]=[];
 constructor(initial:Drawing[]=[]){this.current=initial;}
 push(next:Drawing[]){this.past=[...this.past.slice(-49),this.current];this.current=next;this.future=[];return next;}
 undo(){const last=this.past.pop();if(last){this.future.push(this.current);this.current=last;}return this.current;}
 redo(){const next=this.future.pop();if(next){this.past.push(this.current);this.current=next;}return this.current;}
}
