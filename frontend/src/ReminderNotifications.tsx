import {useEffect,useRef} from 'react';
import {toast} from 'sonner';
import {startTradingPolling} from './TradingToolsPanel';
type ReminderEvent={id:string;name:string;message:string;created_at_utc:string;conversation_id?:string};
const KEY='gold-desk-reminder-seen-v1';
export function freshReminderEvents(rows:ReminderEvent[],seen:Set<string>,now=Date.now()){
 const selected=new Set<string>();return rows.filter(row=>{const time=Date.parse(row.created_at_utc);if(!row.id||seen.has(row.id)||selected.has(row.id)||!Number.isFinite(time)||time>now||now-time>600000)return false;selected.add(row.id);return true;}).slice(0,5);
}
export default function ReminderNotifications({onView}:{onView:(conversationId?:string)=>void}){
 const callback=useRef(onView);callback.current=onView;
 useEffect(()=>{
  if(import.meta.env.MODE==='pages')return;
  let seen=new Set<string>();try{const stored=JSON.parse(localStorage.getItem(KEY)??'[]');if(Array.isArray(stored))seen=new Set(stored.filter(v=>typeof v==='string').slice(-200));}catch{}
  return startTradingPolling(async signal=>{
    const response=await fetch('/api/trading/alerts',{cache:'no-store',signal});
    if(!response.ok)throw Error();return await response.json();
  },data=>{
    if(data.status!=='AVAILABLE')return;
    const rows=Array.isArray(data.events)?data.events as ReminderEvent[]:[];
    for(const event of freshReminderEvents(rows,seen))toast.message(event.name,{description:event.message,duration:10000,action:{label:'查看',onClick:()=>callback.current(event.conversation_id)}});
    for(const event of rows)if(typeof event.id==='string')seen.add(event.id);
    seen=new Set([...seen].slice(-200));try{localStorage.setItem(KEY,JSON.stringify([...seen]));}catch{}
  },()=>{});
 },[]);
 return null;
}
