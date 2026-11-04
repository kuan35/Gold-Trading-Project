import {useEffect,useRef,useState,type FormEvent} from 'react';
import Chart from './Chart';import {LatestTradingRequest} from './TradingToolsPanel';import type {Bar} from './types';
import {historyDateInput,historyTimestamp,mergeHistoryBars,historyGaps,type HistoryZone} from './historyBrowserModel';
type Source={id:string;label:string;first:number;last:number;count:number};
type Metadata={status:string;indexing:boolean;error?:string|null;first:number|null;last:number|null;sources:Source[]};
type Window={status:string;reason?:string;bars:Bar[];source:string|null;source_label?:string;quote_side?:string;volume_basis?:string;interval:string;requested_at:number;anchor_time?:number;shifted:boolean;has_before:boolean;has_after:boolean;gaps:Array<{from_time:number;to_time:number;seconds:number}>};
type Interval='5m'|'15m'|'1h';type Direction='around'|'before'|'after';
async function request<T>(path:string,signal:AbortSignal,method='GET'):Promise<T>{const r=await fetch('/api/history'+path,{method,signal,cache:'no-store'}),body=await r.json();if(!r.ok)throw Error(typeof body.detail==='string'?body.detail:'歷史資料查詢失敗。');return body;}
export default function HistoryBrowser({light}:{light:boolean}){
 const [meta,setMeta]=useState<Metadata|null>(null),[data,setData]=useState<Window|null>(null),[interval,setInterval]=useState<Interval>('5m'),[source,setSource]=useState('auto'),[zone,setZone]=useState<HistoryZone>('Taiwan'),[input,setInput]=useState(''),[error,setError]=useState(''),[pending,setPending]=useState(false),[reset,setReset]=useState(0),[metaCycle,setMetaCycle]=useState(0),[viewRange,setViewRange]=useState<{from:number;to:number}|null>(null);
 const read=useRef(new LatestTradingRequest()),metaRead=useRef(new LatestTradingRequest()),lastAt=useRef<number|null>(null),dataRef=useRef(data),busy=useRef(false);dataRef.current=data;
 const display=(t:number)=>historyDateInput(t,zone).replace('T',' ')+(zone==='Taiwan'?' 台灣':' UTC');
 useEffect(()=>{let live=true,timer:number|undefined;const poll=async()=>{await metaRead.current.run(signal=>request<Metadata>('/metadata',signal),m=>{if(!live)return;setMeta(m);if(m.indexing)timer=window.setTimeout(()=>void poll(),1500);},e=>setError(e instanceof Error?e.message:'讀取資料範圍失敗'));};void poll();return()=>{live=false;clearTimeout(timer);metaRead.current.cancel();};},[metaCycle]);
 useEffect(()=>()=>read.current.cancel(),[]);
 const load=(at:number,iv:Interval=interval,src=source,direction:Direction='around',append=false)=>{
  if(append&&busy.current)return;busy.current=true;setPending(true);setError('');if(direction==='around'){lastAt.current=at;setInput(historyDateInput(at,zone));}
  const old=dataRef.current;
  void read.current.run(signal=>request<Window>('/bars?'+new URLSearchParams({at:String(at),interval:iv,source:src,direction,limit:'600'}),signal),value=>{
   busy.current=false;setPending(false);
   if(append&&old&&value.status==='AVAILABLE'&&value.source===old.source&&value.interval===old.interval){const bars=mergeHistoryBars(old.bars,value.bars,direction as 'before'|'after');setData({...value,bars,requested_at:old.requested_at,anchor_time:old.anchor_time,shifted:old.shifted,has_before:direction==='before'?value.has_before:old.has_before||bars[0].time>old.bars[0].time,has_after:direction==='after'?value.has_after:old.has_after||bars.at(-1)!.time<old.bars.at(-1)!.time,gaps:historyGaps(bars,old.interval)});}
   else{setData(value);const index=value.bars.findIndex(b=>b.time===value.anchor_time);setViewRange(index>=0?{from:Math.max(0,index-70),to:Math.min(value.bars.length+5,index+30)}:null);setReset(v=>v+1);if(value.status==='AVAILABLE'){setInterval(iv);if(direction!=='around'&&value.anchor_time){lastAt.current=value.anchor_time;setInput(historyDateInput(value.anchor_time,zone));}}}
  },e=>{busy.current=false;setPending(false);setError(e instanceof Error?e.message:'歷史查詢失敗，請重試。');});
 };
 useEffect(()=>{if(meta?.status==='AVAILABLE'&&meta.last!==null&&lastAt.current===null)load(meta.last);},[meta?.status,meta?.last]);
 const jump=(e:FormEvent)=>{e.preventDefault();const at=historyTimestamp(input,zone);if(at===null){setError('請填寫有效日期與時間。');return;}load(at);};
 const page=(direction:'before'|'after',append=false)=>{const d=dataRef.current;if(!d?.bars.length||pending)return;load(direction==='before'?d.bars[0].time:d.bars.at(-1)!.time,d.interval as Interval,d.source??source,direction,append);};
 const sourceRange=source==='auto'?meta:meta?.sources.find(s=>s.id===source);
 const refresh=()=>{void metaRead.current.run(signal=>request<Metadata>('/refresh',signal,'POST'),m=>{setMeta(m);setMetaCycle(v=>v+1);},e=>setError(String(e)));};
 return <section id="market-workspace" tabIndex={-1} className="history-browser" aria-label="完整歷史看盤">
  <div className="history-heading"><div><h2>歷史看盤</h2><p>選時間看過去行情；此處可看到所選時點之後的歷史走勢，不改動交易演練。</p></div><button type="button" disabled={meta?.indexing} onClick={refresh}>{meta?.indexing?'建立資料索引中…':'重新整理資料索引'}</button></div>
  <form onSubmit={jump} className="history-controls"><label>查看時間<input aria-label="歷史查看時間" type="datetime-local" step="60" min="2020-01-01T00:00" value={input} onChange={e=>setInput(e.target.value)} required/></label>
   <label>時區<select aria-label="歷史時區" value={zone} onChange={e=>{const z=e.target.value as HistoryZone,at=historyTimestamp(input,zone);setZone(z);if(at!==null)setInput(historyDateInput(at,z));}}><option value="Taiwan">台灣時間 UTC+8</option><option value="UTC">UTC</option></select></label>
   <label>行情來源<select aria-label="歷史行情來源" value={source} onChange={e=>{setSource(e.target.value);if(lastAt.current!==null)load(lastAt.current,interval,e.target.value);}}><option value="auto">依日期選擇可用來源</option>{meta?.sources.map(s=><option key={s.id} value={s.id}>{s.label}</option>)}</select></label>
   <button className="primary" disabled={pending||meta?.status!=='AVAILABLE'}>跳轉</button><button type="button" disabled={pending||!sourceRange?.last} onClick={()=>sourceRange?.last&&load(sourceRange.last)}>最新已保存行情</button>
  </form>
  <div className="history-navigation"><div className="segments" aria-label="歷史K線週期">{(['5m','15m','1h'] as const).map(iv=><button type="button" key={iv} aria-pressed={interval===iv} className={iv===interval?'active':''} onClick={()=>{setInterval(iv);if(lastAt.current!==null)load(lastAt.current,iv);}}>{iv==='5m'?'5 分':iv==='15m'?'15 分':'1 小時'}</button>)}</div><button type="button" disabled={pending||!data?.has_before} onClick={()=>page('before')}>更早一段</button><button type="button" disabled={pending||!data?.has_after} onClick={()=>page('after')}>更晚一段</button></div>
  <div className="history-status" role="status">{sourceRange?.first!=null&&sourceRange.last!=null?<span>可用範圍 {display(sourceRange.first)} ～ {display(sourceRange.last)}；不代表中間無缺口。</span>:<span>{meta?.indexing?'首次整理歷史資料，請稍候；可先使用其他頁面。':'尚無歷史資料。請匯入授權runtime包，或依安裝說明下載本人的DEMO歷史行情。'}</span>}{pending&&<span>正在載入所選時段…</span>}</div>
  {(error||meta?.error)&&<p role="alert">{error||meta?.error}</p>}
  {data?.status==='AVAILABLE'&&data.bars.length?<><div className="history-chart-label"><strong>{data.source_label} · {data.quote_side} · {data.interval}</strong><span>定位 {display(data.anchor_time??data.requested_at)} · 目前圖表 {display(data.bars[0].time)} ～ {display(data.bars.at(-1)!.time)}</span></div>
   {data.shifted&&<p className="history-gap" role="status">所選時間沒有完整K棒，已定位到 {data.anchor_time&&display(data.anchor_time)}；可能是休市、形成中或資料缺口。</p>}
   <div className="history-chart"><Chart logicalRange={viewRange} markers={data.anchor_time?[{time:data.anchor_time,position:'aboveBar',color:'#d6af68',shape:'circle',text:'定位時間'}]:[]} timeZone={zone} key={`${data.source}:${data.interval}:${reset}`} bars={data.bars} light={light} showVolume={data.bars.some(b=>b.volume!==undefined)} scope={`history:${data.source}:${data.interval}`} ariaLabel="歷史看盤K線，與模擬交易時間獨立" onHistoryEdge={edge=>{if(data.bars.length<2400&&((edge==='before'&&data.has_before)||(edge==='after'&&data.has_after)))page(edge,true);}}/></div>
   <p className="fine">載入 {data.bars.length} 棒 · 量：{data.volume_basis} · 向圖表邊緣拖曳可載入鄰近資料，最多保留2400棒；可用前後一段繼續瀏覽。</p>
   {!!data.gaps.length&&<details className="history-gaps"><summary>此段有 {data.gaps.length} 處休市或資料缺口</summary>{data.gaps.slice(0,8).map(g=><p key={g.from_time}>{display(g.from_time)} ～ {display(g.to_time)}，未補價格或量。</p>)}</details>}
  </>:data&&<p className="history-empty" role="status">{data.reason??(data.status==='OUT_OF_RANGE'?'此日期不在所選來源的可用範圍。':'此週期尚無完整K棒，請換日期、來源或週期。')}</p>}
 </section>;
}
