import type {Bar,BarsResponse,Marker,Order} from './types';

/** Known fills anchor to the last closed candle; never fabricate an OHLC bar. */
export function tradeChart(all:Bar[],orders:Order[],seconds:number,source:string,interval:string,focus?:string):BarsResponse {
  const selected=focus?orders.find(o=>o.id===focus):undefined;
  if(focus&&!selected)throw Error('成交紀錄不存在，請重新選擇');
  const positionId=selected?.position_id||(selected&&selected.action!=='CLOSE'?selected.id:undefined);
  const related=selected?orders.filter(o=>o.id===selected.id||(positionId&&(o.id===positionId||o.position_id===positionId))):[];
  let bars=all.slice(-250);
  if(selected){
    const times=related.map(o=>Number(o.time));
    const start=all.map(b=>b.time<=Math.min(...times)-1).lastIndexOf(true);
    const end=all.map(b=>b.time<=Math.max(...times)-1).lastIndexOf(true);
    bars=all.slice(Math.max(0,start-100),Math.min(all.length,end+41));
  }
  const markers:Marker[]=orders.flatMap(o=>{
    if(!bars.length||Number(o.time)<bars[0].time)return [];
    if(bars.at(-1)?.time!==all.at(-1)?.time&&Number(o.time)>bars.at(-1)!.time+seconds)return [];
    const anchor=bars.slice().reverse().find(b=>b.time<=Math.floor((Number(o.time)-1)/seconds)*seconds);
    if(!anchor)return [];
    const buy=o.side==='BUY';
    return [{id:o.id,position_id:o.position_id,action:o.action,time:anchor.time,price:o.price,executed_at:Number(o.time),
      time_precision:o.reason?.startsWith('STOP_')||o.reason?.startsWith('TAKE_')?'bar':'snapshot',
      position:buy?'belowBar':'aboveBar',color:buy?'#44c4b0':'#e47c80',shape:buy?'arrowUp':'arrowDown',
      text:(o.action==='CLOSE'?'平倉':o.action==='FIRST'?'首筆':'加單')+' '+o.lot}];
  });
  return {bars,markers:markers.sort((a,b)=>a.time-b.time||a.executed_at!-b.executed_at!),source,interval,
    focus:selected?{selected_id:selected.id,order_ids:related.map(o=>o.id),orders:related,
      pairing:related.length>1?'linked':selected.action!=='CLOSE'?'open':'unavailable',
      note:'箭頭標示買賣方向與時間，成交價看標籤與價格線；時間貼齊當時最後已收完的K棒。停損／停利只知道觸發K棒，並非精確成交秒。'}:null};
}
