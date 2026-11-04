import {useEffect,useMemo,useRef,useState,type PointerEvent as ReactPointerEvent} from 'react';
import type {ChartRuntime} from './ChartWorkspaceTools';
import type {ISeriesApi,IPriceLine} from 'lightweight-charts';
export type DraftChartState={side:'BUY'|'SELL'|null;order_type:'MARKET'|'LIMIT'|null;limit_price:string;sl:string;tp:string;entry_price?:string|null;digits?:number;disabled?:boolean;onPatch:(patch:{limit_price?:string;sl?:string;tp?:string})=>void};
export type DraftLineSeries=Pick<ISeriesApi<'Candlestick'>,'createPriceLine'|'removePriceLine'>;
type LevelKey='entry'|'sl'|'tp';
type DraftPatch=Parameters<DraftChartState['onPatch']>[0];
export type DraftLevel={key:LevelKey;price:number;draggable:boolean;label:string};
const labels={entry:'擬進場',sl:'停損',tp:'停利'};
const colors={entry:'#d6af68',sl:'#e47e88',tp:'#59cda7'};
const positive=(value:unknown)=>typeof value==='string'&&value.trim()!==''&&Number.isFinite(Number(value))&&Number(value)>0?Number(value):null;
const validDigits=(digits:number)=>Number.isInteger(digits)&&digits>=0&&digits<=8;
const field=(key:LevelKey)=>key==='entry'?'limit_price':key;

// Floats describe chart coordinates only. The backend validates the returned decimal strings.
export function draftChartLevels(draft:DraftChartState):DraftLevel[]{
 if(!draft.side||!draft.order_type||!validDigits(draft.digits??2))return [];
 const entry=positive(draft.order_type==='MARKET'?draft.entry_price:draft.limit_price);
 if(entry===null)return [];
 const result:DraftLevel[]=[{key:'entry',price:entry,draggable:!draft.disabled&&draft.order_type==='LIMIT',label:labels.entry}];
 const sign=draft.side==='BUY'?1:-1;
 for(const key of ['sl','tp'] as const){const price=positive(draft[key]);if(price===null)continue;
  const delta=(price-entry)*sign;
  if(key==='sl'?delta>=0:delta<=0)continue;
  result.push({key,price,draggable:!draft.disabled,label:labels[key]});
 }
 return result;
}

export function priceFromY(y:number,height:number,convert:(y:number)=>number|null,digits=2):string|null{
 if(!Number.isFinite(height)||height<=0||!Number.isFinite(y)||y<0||y>height||!validDigits(digits))return null;
 try{const value=convert(y);if(value===null||!Number.isFinite(value)||value<=0)return null;
  const fixed=value.toFixed(digits);return Number(fixed)>0?fixed:null;
 }catch{return null;}
}

export function stepDraftPrice(draft:DraftChartState,key:LevelKey,arrow:string):DraftPatch|null{
 const level=draftChartLevels(draft).find(level=>level.key===key),digits=draft.digits??2;
 if(!level?.draggable||!validDigits(digits)||!['ArrowUp','ArrowDown'].includes(arrow))return null;
 const next=level.price+(arrow==='ArrowUp'?1:-1)*10**-digits;
 if(!Number.isFinite(next)||next<=0)return null;
 return {[field(key)]:next.toFixed(digits)};
}

export function draftChartGeometry(levels:DraftLevel[],convert:(price:number)=>number|null,height:number,width:number){
 const lines:Array<DraftLevel&{y:number}>=[],zones:Array<{key:'sl'|'tp';top:number;height:number}>=[];
 if(!Number.isFinite(height)||height<=0||!Number.isFinite(width)||width<=0)return {lines,zones};
 const points=new Map<LevelKey,number>();
 for(const level of levels){try{const y=convert(level.price);if(y===null||!Number.isFinite(y))continue;
  points.set(level.key,y);if(y>=0&&y<=height)lines.push({...level,y});
 }catch{/* Removed or unscaled series have no usable coordinates. */}}
 const entry=points.get('entry');
 if(entry!==undefined)for(const key of ['sl','tp'] as const){const y=points.get(key);if(y===undefined)continue;
  const top=Math.max(0,Math.min(entry,y)),bottom=Math.min(height,Math.max(entry,y));
  if(bottom>top)zones.push({key,top,height:bottom-top});
 }
 return {lines,zones};
}

export class DraftPriceLines{
 private lines=new Map<LevelKey,{line:IPriceLine;price:number}>();
 constructor(private series:DraftLineSeries){}
 update(levels:DraftLevel[]){
  for(const [key,entry] of this.lines)if(!levels.some(level=>level.key===key)){this.series.removePriceLine(entry.line);this.lines.delete(key);}
  for(const level of levels){const entry=this.lines.get(level.key);
   if(entry){if(entry.price!==level.price){entry.line.applyOptions({price:level.price});entry.price=level.price;}}
   else this.lines.set(level.key,{price:level.price,line:this.series.createPriceLine({price:level.price,color:colors[level.key],lineWidth:1,lineStyle:2,axisLabelVisible:true,title:'草稿 '+level.label})});
  }
 }
 dispose(remove=true){if(remove)for(const {line} of this.lines.values())this.series.removePriceLine(line);this.lines.clear();}
}

type Drag={key:LevelKey;pointerId:number;signature:string;value:string;changed:boolean};
const emptyMetrics={top:0,left:0,width:0,height:0};
export default function DraftChartOverlay({runtime,draft}:{runtime:ChartRuntime|null;draft:DraftChartState}){
 const root=useRef<HTMLDivElement>(null),layer=useRef<DraftPriceLines|null>(null),drag=useRef<Drag|null>(null),latest=useRef(draft);
 const [metrics,setMetrics]=useState(emptyMetrics),[,repaint]=useState(0),[moving,setMoving]=useState<{key:LevelKey;value:string}|null>(null);
 latest.current=draft;
 const signature=JSON.stringify([draft.side,draft.order_type,draft.limit_price,draft.sl,draft.tp,draft.order_type==='MARKET'?draft.entry_price:null,draft.digits,draft.disabled]);
 const dragSignature=JSON.stringify([draft.side,draft.order_type,draft.limit_price,draft.sl,draft.tp,draft.digits,draft.disabled]);
 const currentSignature=useRef(dragSignature);currentSignature.current=dragSignature;
 const baseLevels=useMemo(()=>draftChartLevels(draft),[signature]);
 const levels=useMemo(()=>baseLevels.map(level=>moving?.key===level.key?{...level,price:Number(moving.value)}:level),[baseLevels,moving]);
 useEffect(()=>{drag.current=null;setMoving(null);},[dragSignature,runtime]);
 useEffect(()=>{
  if(!runtime||runtime.active===false)return;
  const current=new DraftPriceLines(runtime.candles);layer.current=current;
  return()=>{current.dispose(runtime.active!==false);if(layer.current===current)layer.current=null;drag.current=null;};
 },[runtime]);
 useEffect(()=>{if(runtime&&runtime.active!==false)layer.current?.update(levels);},[runtime,levels]);
 useEffect(()=>{
  if(!runtime||runtime.active===false)return;
  const r=runtime,chart=r.chart,scale=chart.timeScale();let frame=0,disposed=false;
  const paint=()=>{if(frame||disposed)return;frame=requestAnimationFrame(()=>{frame=0;if(disposed||r.active===false)return;
   try{const pane=r.candles.getPane(),size=chart.paneSize(pane.paneIndex()),container=root.current?.parentElement;
    const paneRect=pane.getHTMLElement()?.getBoundingClientRect(),parentRect=container?.getBoundingClientRect();
    const height=pane.getHeight(),width=size.width;
    const next=parentRect&&parentRect.width>0&&parentRect.height>0&&height>0&&width>0?{
     top:paneRect?paneRect.top-parentRect.top:0,left:paneRect?paneRect.left-parentRect.left:0,width,height}:emptyMetrics;
    setMetrics(old=>Object.keys(next).every(k=>old[k as keyof typeof old]===next[k as keyof typeof next])?old:next);repaint(v=>v+1);
   }catch{setMetrics(emptyMetrics);}
  });};
  const element=chart.chartElement();
  scale.subscribeVisibleLogicalRangeChange(paint);scale.subscribeSizeChange(paint);
  chart.subscribeCrosshairMove(paint);r.candles.subscribeDataChanged(paint);
  element.addEventListener('pointermove',paint,{passive:true});element.addEventListener('wheel',paint,{passive:true});
  const observer=typeof ResizeObserver==='undefined'?null:new ResizeObserver(paint);
  observer?.observe(element);const paneElement=r.candles.getPane().getHTMLElement();if(paneElement)observer?.observe(paneElement);
  paint();
  return()=>{disposed=true;observer?.disconnect();if(frame)cancelAnimationFrame(frame);
   element.removeEventListener('pointermove',paint);element.removeEventListener('wheel',paint);
   if(r.active!==false){scale.unsubscribeVisibleLogicalRangeChange(paint);scale.unsubscribeSizeChange(paint);chart.unsubscribeCrosshairMove(paint);r.candles.unsubscribeDataChanged(paint);}
  };
 },[runtime,!!baseLevels.length]);
 if(!runtime||runtime.active===false||!baseLevels.length)return null;
 const geometry=draftChartGeometry(levels,price=>runtime.candles.priceToCoordinate(price),metrics.height,metrics.width);
 const pointerValue=(event:ReactPointerEvent)=>{const rect=root.current?.getBoundingClientRect();return rect?priceFromY(event.clientY-rect.top,metrics.height,y=>runtime.candles.coordinateToPrice(y),latest.current.digits??2):null;};
 const release=(event:ReactPointerEvent)=>{try{if(event.currentTarget.hasPointerCapture(event.pointerId))event.currentTarget.releasePointerCapture(event.pointerId);}catch{/* The DOM may already be gone. */}};
 const end=(event:ReactPointerEvent,cancel=false)=>{
  const current=drag.current;if(!current||current.pointerId!==event.pointerId)return;
  event.preventDefault();event.stopPropagation();drag.current=null;release(event);setMoving(null);
  if(cancel||latest.current.disabled||current.signature!==currentSignature.current||runtime.active===false)return;
  const value=pointerValue(event)??current.value;
  if(current.changed&&value)latest.current.onPatch({[field(current.key)]:value});
 };
 return <div ref={root} className="gd-draft-overlay" aria-label="目前草稿價位；圖上調整後仍須檢查並確認" style={{position:'absolute',top:metrics.top,left:metrics.left,width:metrics.width,height:metrics.height,pointerEvents:'none',overflow:'hidden',zIndex:3}}>
  {geometry.zones.map(zone=><div key={zone.key} aria-hidden="true" className={`gd-draft-zone gd-draft-zone-${zone.key}`} style={{position:'absolute',left:0,right:0,top:zone.top,height:zone.height}}/>)}
  {geometry.lines.map(level=><div key={level.key} className={`gd-draft-line gd-draft-line-${level.key}`} data-draft-level={level.key} style={{position:'absolute',top:level.y,left:0,right:0,transform:'translateY(-50%)'}}>
   {level.draggable?<button type="button" className="gd-draft-handle" aria-label={`調整草稿${level.label}`} title="拖曳後放開以填入草稿，方向鍵每次調整一個價格級距" style={{pointerEvents:'auto',touchAction:'none',cursor:'ns-resize'}}
    onKeyDown={event=>{const patch=stepDraftPrice(latest.current,level.key,event.key);if(!patch)return;event.preventDefault();event.stopPropagation();latest.current.onPatch(patch);}}
    onPointerDown={event=>{if(latest.current.disabled||event.button!==0||runtime.active===false)return;event.preventDefault();event.stopPropagation();
     drag.current={key:level.key,pointerId:event.pointerId,signature:currentSignature.current,value:level.price.toFixed(draft.digits??2),changed:false};event.currentTarget.setPointerCapture(event.pointerId);}}
    onPointerMove={event=>{const current=drag.current;if(!current||current.pointerId!==event.pointerId||latest.current.disabled||current.signature!==currentSignature.current)return;
     event.preventDefault();event.stopPropagation();const value=pointerValue(event);if(value===null)return;current.changed=current.changed||value!==current.value;current.value=value;setMoving({key:current.key,value});}}
    onPointerUp={event=>end(event)} onPointerCancel={event=>end(event,true)} onLostPointerCapture={event=>end(event,true)}>{level.label} {level.price.toFixed(validDigits(draft.digits??2)?draft.digits??2:2)}</button>
    :<span className="gd-draft-label">{level.label} {level.price.toFixed(validDigits(draft.digits??2)?draft.digits??2:2)}{level.key==='entry'&&draft.order_type==='MARKET'?' · 市價':''}</span>}
  </div>)}
 </div>;
}
