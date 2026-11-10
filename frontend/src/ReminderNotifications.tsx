import {useEffect,useRef,type RefObject} from 'react';
import {toast} from 'sonner';
import {startTradingPolling} from './TradingToolsPanel';
type ReminderEvent={id:string;name:string;message:string;created_at_utc:string;conversation_id?:string};
const KEY='gold-desk-reminder-seen-v1',LIVE_KEY='gold-desk-live-reminder-seen-v1';
type View=(conversationId?:string)=>void;
export function freshReminderEvents(rows:ReminderEvent[],seen:Set<string>,now=Date.now()){
 const selected=new Set<string>();return rows.filter(row=>{const time=Date.parse(row.created_at_utc);if(!row.id||seen.has(row.id)||selected.has(row.id)||!Number.isFinite(time)||time>now||now-time>600000)return false;selected.add(row.id);return true;}).slice(0,5);
}
/** DEMO reminders always notify; LIVE is polled only while LIVE is selected, so DEMO use never opens a LIVE connection. */
export function reminderSources(environment:'demo'|'live'='demo'){
 return [{path:'/api/trading/alerts',key:KEY,label:'',enabled:true},
  {path:'/api/live/trading/alerts',key:LIVE_KEY,label:'LIVE · ',enabled:environment==='live'}];
}
function useReminderSource({path,key,label,enabled}:ReturnType<typeof reminderSources>[number],callback:RefObject<View>){
 useEffect(()=>{
  if(import.meta.env.MODE==='pages'||!enabled)return;
  let seen=new Set<string>();try{const stored=JSON.parse(localStorage.getItem(key)??'[]');if(Array.isArray(stored))seen=new Set(stored.filter(v=>typeof v==='string').slice(-200));}catch{}
  return startTradingPolling(async signal=>{
    const response=await fetch(path,{cache:'no-store',signal});
    if(!response.ok)throw Error();return await response.json();
  },data=>{
    if(data.status!=='AVAILABLE')return;
    const rows=Array.isArray(data.events)?data.events as ReminderEvent[]:[];
    for(const event of freshReminderEvents(rows,seen))toast.message(label+event.name,{description:event.message,duration:10000,action:{label:'查看',onClick:()=>callback.current?.(event.conversation_id)}});
    for(const event of rows)if(typeof event.id==='string')seen.add(event.id);
    seen=new Set([...seen].slice(-200));try{localStorage.setItem(key,JSON.stringify([...seen]));}catch{}
  },()=>{});
 },[path,key,label,enabled,callback]);
}
export default function ReminderNotifications({onView,environment='demo'}:{onView:View;environment?:'demo'|'live'}){
 const callback=useRef(onView);callback.current=onView;
 const [demo,live]=reminderSources(environment);
 useReminderSource(demo,callback);useReminderSource(live,callback);
 return null;
}
