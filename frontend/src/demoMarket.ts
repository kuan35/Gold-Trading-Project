import {useEffect,useState} from 'react';
import {api} from './api';
import type {Bar} from './types';

export type BrokerEnvironment='demo'|'live';
export type DemoMarket = {
  source:'ctrader_demo_xauusd'|'ctrader_live_xauusd';environment:BrokerEnvironment;connection_status:string;
  token_scope:string;order_connection:boolean;
  symbol:{lot_size_cents:number;min_volume_cents:number;max_volume_cents:number;step_volume_cents:number;digits:number}|null;
  quote:{status:string;bid:string|null;ask:string|null;source_time_utc:string|null;age_seconds:number|null};
  account:{status:string;balance:string|null;equity:string|null;currency:string|null;account_last4?:string|null;account_leverage?:string|null;
    pnl_status?:string;pnl_updated_at_utc?:string;net_unrealized_pnl?:string|null;xau_net_unrealized_pnl?:string|null;
    positions:{id:string;side:'BUY'|'SELL';volume_units:string;lot?:string;entry:string|null;sl:string|null;tp:string|null;trailing_stop_loss?:boolean;guaranteed_stop_loss?:boolean;opened_at_utc?:string|null;net_pnl?:string|null;gross_pnl?:string|null;price_return_pct?:string|null;estimated_margin_roi_pct?:string|null;margin_roi_pct?:string|null;actual_margin_roi_pct?:string|null;margin_return_source?:string;used_margin?:string|null;return_currency?:string|null;return_basis?:string;return_reason?:string|null}[];
    pending_orders:{id:string;side:'BUY'|'SELL';volume_units:string;lot?:string;limit_price:string|null;stop_price?:string|null;sl?:string|null;tp?:string|null;created_at_utc?:string|null;status?:string;order_type?:string;intent?:string;position_id?:string}[];
    all_positions_count:number;all_pending_orders_count:number;updated_at_utc:string}|null;
};

export type DemoBars={source:string;environment:BrokerEnvironment;status:string;interval:string;closed_only:true;bars:Bar[]};

export function brokerConnectionIssue(market:DemoMarket|null):string|null{
  if(market?.environment!=='live')return null;
  switch(market.connection_status){
    case 'ACCOUNT_ID_REQUIRED':return 'LIVE 尚未設定 Open API 帳戶 ID';
    case 'CREDENTIALS_MISSING':return 'LIVE 授權資料尚未填妥';
    case 'LIVE_ENVIRONMENT_REQUIRED':return 'LIVE 設定檔的環境需設為 live';
    case 'NOT_CONFIGURED':return 'LIVE 設定檔尚未建立';
    case 'LIVE_READONLY_CONNECTION_ERROR':return 'LIVE 連線失敗，請檢查授權與網路';
    default:return null;
  }
}

export function useDemoMarket(enabled=true){
  const [market,setMarket]=useState<DemoMarket|null>(null);
  useEffect(()=>{
    if(!enabled||import.meta.env.MODE==='pages'){setMarket(null);return;}
    let active=true;let timer:number|undefined;
    const refresh=async()=>{
      try{const value=await api<DemoMarket>('/broker/market');if(active)setMarket(value);}
      catch{if(active)setMarket(null);}
      if(active)timer=window.setTimeout(refresh,1000);
    };
    void refresh();
    return()=>{active=false;if(timer)window.clearTimeout(timer);};
  },[enabled]);
  return market;
}

export function useLiveMarket(enabled:boolean){
  const [market,setMarket]=useState<DemoMarket|null>(null);
  useEffect(()=>{
    if(!enabled||import.meta.env.MODE==='pages'){setMarket(null);return;}
    let active=true;let timer:number|undefined;
    const refresh=async()=>{
      try{const value=await api<DemoMarket>('/live/market');if(active)setMarket(value.environment==='live'?value:null);}
      catch{if(active)setMarket(null);}
      if(active)timer=window.setTimeout(refresh,1000);
    };
    void refresh();return()=>{active=false;if(timer)window.clearTimeout(timer);};
  },[enabled]);
  return market;
}

export function demoQuoteLabel(market:DemoMarket|null):string{
  const environment=market?.environment==='live'?'LIVE':'DEMO';
  if(import.meta.env.MODE==='pages')return 'DEMO 報價需本機服務';
  if(!market)return `${environment} 報價連線中`;
  const issue=brokerConnectionIssue(market);
  if(issue)return issue;
  if(market.quote.status==='CURRENT')return `cTrader ${environment} · 最新 tick`;
  if(market.quote.status==='STALE')return `cTrader ${environment} · 報價過期`;
  return `cTrader ${environment} · ${market.connection_status==='CONNECTED'?'等待報價':'未連線'}`;
}
