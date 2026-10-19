import type {Draft,Retrieval,State} from './types';

const endpoint=import.meta.env.VITE_GROQ_PROXY_URL?.trim().replace(/\/$/,'') || '';
export const groqProxyAvailable=import.meta.env.MODE==='pages' && /^https:\/\/[^/]+$/.test(endpoint) && !!import.meta.env.VITE_TURNSTILE_SITE_KEY;
export const turnstileSiteKey=import.meta.env.VITE_TURNSTILE_SITE_KEY || '';

export async function askGroq(message:string,token:string,state:State|null,pool:Retrieval|null,draft:Draft|null):Promise<string>{
  if(!groqProxyAvailable || !state || !token)throw Error('Groq 代理尚未就緒');
  const cases=draft?.retrieval || pool;
  const facts=JSON.stringify({
    source:'synthetic_demo',mode:state.mode,broker_connected:false,clock_utc:state.clock,
    market_last_60_5m_bars:state.market,
    case_comparison:cases?{scope:cases.comparison?.mode||'operation_only',groups:cases.total,wins:cases.wins,losses:cases.losses,flat:cases.flat,unknown:cases.unknown,market_reason:cases.comparison?.reason||'歷史K線時鐘未核實'}:null,
    order:draft?{status:'REVIEW',side:draft.side,lot:draft.lot,price:draft.price,stop_loss_usd:draft.risk.stop_loss_usd}:null,
    note:'當前回放行情與模擬下單為合成資料；案例彙總來自公開的真實交易員紀錄。未連券商；歷史案例的券商時鐘未獨立核實。',
  });
  const response=await fetch(`${endpoint}/explain`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:message.slice(0,500),facts,token}),signal:AbortSignal.timeout(15000)});
  const body=await response.json().catch(()=>({error:'代理回應格式錯誤'}));
  if(!response.ok || typeof body.message!=='string')throw Error(typeof body.error==='string'?body.error:'Groq 暫時無法回答');
  return body.message;
}
