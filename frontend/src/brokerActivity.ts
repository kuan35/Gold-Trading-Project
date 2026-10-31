import {useEffect,useState} from 'react';
import {api} from './api';

export type BrokerRecord={id?:string;draft_id?:string;client_order_id?:string|null;order_id?:string|null;position_id?:string|null;
 side?:string|null;lot?:string|null;filled_lot?:string|null;order_type?:string|null;status:string;
 price?:string|null;limit_price?:string|null;execution_price?:string|null;sl?:string|null;tp?:string|null;
 created_at_utc?:string|null;updated_at_utc?:string|null;executed_at_utc?:string|null;currency?:string|null;
 error_code?:string|null;account_scope?:string;intent?:'OPEN'|'CLOSE'|'PROTECT'|'CANCEL';role?:string;realized_gross_pnl?:string|null;commission?:string|null;swap?:string|null};
export type BrokerHistory={status:string;items:BrokerRecord[];has_more:boolean;from_utc?:string;to_utc?:string;updated_at_utc?:string};
export type BrokerActivity={source:'ctrader_demo_xauusd';environment:'demo';connection_status:string;account_scope:string;updated_at_utc:string;
 submissions:{items:BrokerRecord[];total:number;has_more:boolean;offset:number;limit:number};broker_orders:BrokerHistory;broker_deals:BrokerHistory};

export function useBrokerActivity(offset:number){
 const [activity,setActivity]=useState<BrokerActivity|null>(null),[error,setError]=useState('');
 useEffect(()=>{
  if(import.meta.env.MODE==='pages')return;
  let active=true,timer:number|undefined;
  setActivity(null);setError('');
  const refresh=async()=>{
   try{const value=await api<BrokerActivity>(`/broker/activity?offset=${offset}&limit=50`);if(active){setActivity(value);setError('');}}
   catch{if(active)setError('交易紀錄讀取失敗；保留最後一次資料，請確認本機服務與券商連線。');}
   if(active)timer=window.setTimeout(refresh,2000);
  };
  void refresh();return()=>{active=false;if(timer)window.clearTimeout(timer);};
 },[offset]);
 return {activity,error};
}
