import {useEffect,useState} from 'react';
import {api} from './api';
import type {DemoBars,BrokerEnvironment} from './demoMarket';
import type {LiveChartFrame} from './liveCandles';

export function useLiveCandles(interval:'5m'|'15m'|'1h',environment:BrokerEnvironment='demo'){
 const [frame,setFrame]=useState<LiveChartFrame|null>(null),[pending,setPending]=useState(import.meta.env.MODE!=='pages');
 useEffect(()=>{
  if(import.meta.env.MODE==='pages')return;
  let active=true,events:EventSource|null=null,timer:number|undefined,received=false;
  setFrame(null);setPending(true);
  const fallback=async()=>{
   try{const data=await api<DemoBars>(`${environment==='live'?'/live':'/broker'}/bars?interval=${interval}`);
    if(active&&!received&&data.environment===environment&&data.interval===interval)setFrame({...data,closed_only:false,forming:null,forming_status:'WAITING'});
   }catch{if(active&&!received)setFrame(null);}
   if(active){setPending(false);timer=window.setTimeout(fallback,15000);}
  };
  const connect=()=>{
   events?.close();events=null;
   if(document.hidden){setFrame(old=>old?{...old,status:'STALE',forming:null}:null);return;}
   events=new EventSource(`/api/${environment==='live'?'live':'broker'}/chart-stream?interval=${interval}`);
   events.onmessage=event=>{if(!active)return;try{
    const data=JSON.parse(event.data) as LiveChartFrame;
    if(data.interval!==interval||data.environment!==environment||!Array.isArray(data.bars))return;
    received=true;setFrame(data);setPending(false);
   }catch{setFrame(old=>old?{...old,status:'STALE',forming:null}:null);}};
   events.onerror=()=>{if(active){received=false;setFrame(old=>old?{...old,status:'STALE',forming:null}:null);}};
  };
  connect();void fallback();document.addEventListener('visibilitychange',connect);
  return()=>{active=false;events?.close();if(timer)window.clearTimeout(timer);document.removeEventListener('visibilitychange',connect);};
 },[interval,environment]);
 return {frame,pending};
}
