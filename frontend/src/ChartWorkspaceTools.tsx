import {useEffect,useRef,useState} from 'react';
import {createPortal} from 'react-dom';
import {LineSeries,HistogramSeries,type IChartApi,type ISeriesApi,type UTCTimestamp,type Logical} from 'lightweight-charts';
import {studyValues,studies,decodeDrawings,DrawingHistory,type Study,type Drawing,type Candle} from './chartWorkspaceModel';
export type ChartRuntime={chart:IChartApi;candles:ISeriesApi<'Candlestick'>;volume?:ISeriesApi<'Histogram'>;averages?:ISeriesApi<'Line'>[];active?:boolean};
const colors=['#d6af68','#8daece','#dc9e68','#b6a2d9','#78b5ac','#be8da1','#95ba80','#d6af68','#8daece','#c19970'];
type Tool='pan'|Drawing['kind'];
const key='gold-desk-chart-studies-v1';
function saved():Study[]{try{const a=JSON.parse(localStorage.getItem(key)??'[]');return Array.isArray(a)?a.filter(s=>studies.includes(s)):[];}catch{return [];}}
export default function ChartWorkspaceTools({runtime,bars,scope,defaultVolume=true,defaultAverages=true}:{runtime:ChartRuntime|null;bars:Candle[];scope:string;defaultVolume?:boolean;defaultAverages?:boolean}){
 const [selected,setSelected]=useState<Study[]>(saved),[volume,setVolume]=useState(defaultVolume),[ma,setMa]=useState(defaultAverages),[tool,setTool]=useState<Tool>('pan'),[text,setText]=useState('註記'),[notice,setNotice]=useState('');
 const [drawings,setDrawings]=useState<Drawing[]>([]),[chosen,setChosen]=useState(''),[revision,setRevision]=useState(0);
 const svg=useRef<SVGSVGElement>(null),history=useRef(new DrawingHistory()),first=useRef<Drawing['points'][0]|null>(null),overlayLines=useRef<ISeriesApi<'Line'|'Histogram'>[]>([]);
 const storeKey='gold-desk-drawings:'+scope;
 const dragCleanup=useRef<()=>void>(()=>{});
 useEffect(()=>()=>dragCleanup.current(),[scope]);
 const commit=(next:Drawing[],push=true)=>{if(push)history.current.push(next);setDrawings([...next]);try{localStorage.setItem(storeKey,JSON.stringify({scope,drawings:next}));}catch{setNotice('瀏覽器未允許保存畫線');}};
 useEffect(()=>{let next:Drawing[]=[];try{next=decodeDrawings(localStorage.getItem(storeKey),scope);}catch{}history.current=new DrawingHistory(next);setDrawings(next);setChosen('');first.current=null;},[scope]);
 useEffect(()=>{try{localStorage.setItem(key,JSON.stringify(selected));}catch{}},[selected]);
 useEffect(()=>{const r=runtime;if(!r||r.active===false)return;const {chart}=r;
  const lines:ISeriesApi<'Line'|'Histogram'>[]=[];
  const paneKinds=['RSI14','MACD','ATR14'].filter(kind=>selected.some(s=>s.startsWith(kind)));
  for(const study of selected){
   const kind=study.startsWith('MACD')?'MACD':study;
   const pane=paneKinds.includes(kind)?paneKinds.indexOf(kind)+1:0;
   const s=chart.addSeries(LineSeries,{color:colors[studies.indexOf(study)],lineWidth:1,lastValueVisible:false,priceLineVisible:false,title:study},pane);
   s.setData(studyValues(study,bars).map(p=>({...p,time:p.time as UTCTimestamp})));lines.push(s);
  }
  if(!r.volume&&volume&&bars.some(b=>b.volume!==undefined)){
   const s=chart.addSeries(HistogramSeries,{priceFormat:{type:'volume'},priceScaleId:'',lastValueVisible:false,priceLineVisible:false});
   s.priceScale().applyOptions({scaleMargins:{top:.84,bottom:0}});s.setData(bars.filter(b=>b.volume!==undefined).map(b=>({time:b.time as UTCTimestamp,value:b.volume!,color:b.close>=b.open?'#59d8a745':'#f58c9345'})));lines.push(s);
  }
  overlayLines.current=lines;
  chart.panes().forEach((pane,i)=>{if(i>0)pane.setHeight(90);});
  const plot=chart.chartElement().parentElement;if(plot)plot.style.minHeight=String(220+Math.max(0,chart.panes().length-1)*90)+'px';
  return()=>{if(r.active!==false)for(const s of lines){try{chart.removeSeries(s);}catch{}}overlayLines.current=[];};
 },[runtime,selected,bars,volume]);
 useEffect(()=>{if(runtime?.active===false)return;runtime?.volume?.applyOptions({visible:volume});runtime?.averages?.forEach(s=>s.applyOptions({visible:ma}));},[runtime,ma,volume,bars]);
 useEffect(()=>{if(!runtime||runtime.active===false)return;const click=(p:{time?:unknown;point?:{x:number;y:number};paneIndex?:number})=>{
  if(tool==='pan'||typeof p.time!=='number'||!p.point||(p.paneIndex??0)>0)return;const price=runtime.candles.coordinateToPrice(p.point.y);if(price===null||price<=0)return;
  const point={time:p.time,price};
  if(tool==='horizontal'||tool==='text'){commit([...history.current.current,{id:crypto.randomUUID(),kind:tool,points:[point],text:tool==='text'?text.slice(0,100):''}]);setTool('pan');}
  else if(!first.current){first.current=point;setNotice('再點第二個端點');}
  else{commit([...history.current.current,{id:crypto.randomUUID(),kind:tool,points:[first.current,point],text:''}]);first.current=null;setTool('pan');setNotice('');}
 };runtime.chart.subscribeClick(click);return()=>{if(runtime.active!==false)runtime.chart.unsubscribeClick(click);};
 },[runtime,tool,text,scope]);
 useEffect(()=>{if(!runtime||runtime.active===false)return;const paint=()=>setRevision(r=>r+1);runtime.chart.timeScale().subscribeVisibleLogicalRangeChange(paint);runtime.chart.subscribeCrosshairMove(paint);
  const ro=new ResizeObserver(paint);if(svg.current)ro.observe(svg.current);return()=>{ro.disconnect();if(runtime.active!==false){runtime.chart.timeScale().unsubscribeVisibleLogicalRangeChange(paint);runtime.chart.unsubscribeCrosshairMove(paint);}};
 },[runtime]);
 const xy=(p:Drawing['points'][0])=>{if(!runtime||runtime.active===false)return null;const {chart,candles}=runtime;let x=chart.timeScale().timeToCoordinate(p.time as UTCTimestamp);
  if(x===null){const i=bars.findIndex(b=>b.time>=p.time);if(i>=0)x=chart.timeScale().logicalToCoordinate(i as Logical);}const y=candles.priceToCoordinate(p.price);return x===null||y===null?null:{x,y};};
 const resizeRange=(factor:number)=>{const t=runtime?.chart.timeScale(),r=t?.getVisibleLogicalRange();if(t&&r){const middle=(r.from+r.to)/2,half=(r.to-r.from)*factor/2;t.setVisibleLogicalRange({from:middle-half,to:middle+half});}};
 const screenshot=()=>{try{const a=document.createElement('a');a.download='gold-desk-chart.png';a.href=runtime!.chart.takeScreenshot().toDataURL();a.click();setNotice('已匯出K線與指標；手動畫線及浮層不含於圖片');}catch{setNotice('圖片匯出失敗');}};
 const drag=(event:React.PointerEvent,id:string,index:number)=>{
  if(!runtime||!svg.current)return;event.preventDefault();event.stopPropagation();const start=history.current.current,rect=svg.current.getBoundingClientRect();let next=start;
  const move=(e:PointerEvent)=>{const logical=runtime.chart.timeScale().coordinateToLogical(e.clientX-rect.left),price=runtime.candles.coordinateToPrice(e.clientY-rect.top);if(logical===null||price===null||price<=0)return;const b=bars[Math.max(0,Math.min(bars.length-1,Math.round(logical)))];if(!b)return;
   next=start.map(d=>d.id===id?{...d,points:d.points.map((p,i)=>i===index?{time:b.time,price}:p)}:d);setDrawings(next);
  };const cleanup=()=>{window.removeEventListener('pointermove',move);window.removeEventListener('pointerup',up);window.removeEventListener('pointercancel',up);};const up=()=>{cleanup();commit(next);};dragCleanup.current=cleanup;
  window.addEventListener('pointermove',move);window.addEventListener('pointerup',up,{once:true});window.addEventListener('pointercancel',up,{once:true});
 };
 return <><div className="gd-chart-tools" aria-label="圖表工具列" data-drawing-scope={scope}><button onClick={()=>resizeRange(.7)} aria-label="放大圖表">＋</button><button onClick={()=>resizeRange(1.4)} aria-label="縮小圖表">－</button><button onClick={()=>runtime?.chart.timeScale().fitContent()}>全段</button><button onClick={()=>runtime?.chart.timeScale().setVisibleLogicalRange({from:Math.max(0,bars.length-80),to:bars.length+5})}>最新80棒</button>
 <details><summary>指標</summary><div className="gd-chart-menu"><label><input type="checkbox" checked={ma} onChange={e=>setMa(e.target.checked)}/>原均線</label><label><input type="checkbox" checked={volume} onChange={e=>setVolume(e.target.checked)}/>tick量（有資料時）</label>{studies.map(s=><label key={s}><input type="checkbox" checked={selected.includes(s)} onChange={e=>setSelected(old=>e.target.checked?[...old,s]:old.filter(v=>v!==s))}/>{s}</label>)}<small>暖機不足不繪製，設定僅影響看圖。</small></div></details>
 <select aria-label="畫線工具" value={tool} onChange={e=>{setTool(e.target.value as Tool);first.current=null;setNotice(e.target.value==='pan'?'':'在K線上點選端點');}}>{([['pan','移動'],['horizontal','水平線'],['trend','趨勢線'],['ray','射線'],['rectangle','矩形'],['text','文字'],['measure','量測']] as const).map(([v,label])=><option key={v} value={v}>{label}</option>)}</select>
 {tool==='text'&&<input aria-label="圖表文字註記" value={text} maxLength={100} onChange={e=>setText(e.target.value)}/>}
 {!!drawings.length&&<select aria-label="選取畫線" value={chosen} onChange={e=>setChosen(e.target.value)}><option value="">選取畫線</option>{drawings.map((d,i)=><option key={d.id} value={d.id}>{i+1} · {d.text||d.kind}</option>)}</select>}
 <button disabled={!drawings.length} onClick={()=>commit(history.current.undo(),false)}>復原</button><button onClick={()=>commit(history.current.redo(),false)}>重做</button><button disabled={!chosen} onClick={()=>{commit(drawings.filter(d=>d.id!==chosen));setChosen('');}}>刪除線</button><button onClick={screenshot}>PNG</button>
 <button onClick={()=>{const frame=svg.current?.closest('.gd-chart-workspace');if(!frame)return;void (document.fullscreenElement?document.exitFullscreen():frame.requestFullscreen()).catch(()=>setNotice('此瀏覽器不支援全螢幕'));}}>全螢幕</button>
 {notice&&<output role="status">{notice}</output>}</div>
 {runtime&&runtime.active!==false&&runtime.chart.chartElement().parentElement&&createPortal(<svg ref={svg} className="gd-drawings" data-revision={revision} aria-label="本機手動畫線" style={{pointerEvents:'none'}}>{drawings.map(d=>{
  const a=xy(d.points[0]),b=d.points[1]?xy(d.points[1]):null;if(!a)return null;
  const stroke=chosen===d.id?'#ffffff':'#e4bd77',events={onClick:(e:React.MouseEvent)=>{e.stopPropagation();setChosen(d.id);},style:{pointerEvents:'stroke' as const,cursor:'pointer'},stroke,strokeWidth:chosen===d.id?3:2};
  const width=svg.current?.clientWidth??800;
  return <g key={d.id}>{d.kind==='horizontal'?<line {...events} x1={0} y1={a.y} x2={width-65} y2={a.y}/>:d.kind==='text'?<text {...events} style={{pointerEvents:'all',cursor:'pointer'}} fill={stroke} x={a.x} y={a.y}>{d.text}</text>:b?d.kind==='rectangle'?<rect {...events} fill="#e4bd7712" x={Math.min(a.x,b.x)} y={Math.min(a.y,b.y)} width={Math.abs(a.x-b.x)} height={Math.abs(a.y-b.y)}/>:<><line {...events} x1={a.x} y1={a.y} x2={d.kind==='ray'?width-65:b.x} y2={d.kind==='ray'&&b.x!==a.x?a.y+(b.y-a.y)*(width-65-a.x)/(b.x-a.x):b.y}/>{d.kind==='measure'&&<text fill={stroke} x={b.x} y={b.y-8}>{(d.points[1].price-d.points[0].price).toFixed(2)} · {((d.points[1].price/d.points[0].price-1)*100).toFixed(2)}%</text>}</>:null}{chosen===d.id&&d.points.map((p,i)=>{const pos=xy(p);return pos?<circle key={i} cx={pos.x} cy={pos.y} r={6} fill="#e4bd77" style={{pointerEvents:'all',cursor:'move'}} onPointerDown={e=>drag(e,d.id,i)}/>:null;})}</g>;
 })}</svg>,runtime.chart.chartElement().parentElement!)}</>;
}
