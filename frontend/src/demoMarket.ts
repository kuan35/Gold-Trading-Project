import {useEffect,useState} from 'react';
import {api} from './api';
import type {Bar} from './types';

export type DemoMarket = {
  source:'ctrader_demo_xauusd';environment:'demo';connection_status:string;
  token_scope:string;order_connection:boolean;
  symbol:{lot_size_cents:number;min_volume_cents:number;max_volume_cents:number;step_volume_cents:number;digits:number}|null;
  quote:{status:string;bid:string|null;ask:string|null;source_time_utc:string|null;age_seconds:number|null};
  account:{status:string;balance:string|null;equity:string|null;currency:string|null;
    pnl_status?:string;pnl_updated_at_utc?:string;net_unrealized_pnl?:string|null;xau_net_unrealized_pnl?:string|null;
    positions:{id:string;side:'BUY'|'SELL';volume_units:string;lot?:string;entry:string|null;sl:string|null;tp:string|null;opened_at_utc?:string|null;net_pnl?:string|null;gross_pnl?:string|null}[];
    pending_orders:{id:string;side:'BUY'|'SELL';volume_units:string;lot?:string;limit_price:string|null;sl?:string|null;tp?:string|null;created_at_utc?:string|null;status?:string;order_type?:string}[];
    all_positions_count:number;all_pending_orders_count:number;updated_at_utc:string}|null;
};

export type DemoBars={source:string;environment:'demo';status:string;interval:string;closed_only:true;bars:Bar[]};

export function useDemoMarket(){
  const [market,setMarket]=useState<DemoMarket|null>(null);
  useEffect(()=>{
    if(import.meta.env.MODE==='pages')return;
    let active=true;let timer:number|undefined;
    const refresh=async()=>{
      try{const value=await api<DemoMarket>('/broker/market');if(active)setMarket(value);}
      catch{if(active)setMarket(null);}
      if(active)timer=window.setTimeout(refresh,1000);
    };
    void refresh();
    return()=>{active=false;if(timer)window.clearTimeout(timer);};
  },[]);
  return market;
}

export function demoQuoteLabel(market:DemoMarket|null):string{
  if(import.meta.env.MODE==='pages')return 'DEMO 報價需本機服務';
  if(!market)return 'DEMO 報價連線中';
  if(market.quote.status==='CURRENT')return 'cTrader DEMO · 最新 tick';
  if(market.quote.status==='STALE')return 'cTrader DEMO · 報價過期';
  return `cTrader DEMO · ${market.connection_status==='CONNECTED'?'等待報價':'未連線'}`;
}
