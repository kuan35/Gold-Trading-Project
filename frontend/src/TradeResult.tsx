import Decimal from 'decimal.js';
import type {Marker} from './types';
export type PriceResult={status:string;entry_price?:string|null;exit_price?:string|null;move_per_oz:string|null;price_return_pct:string|null;margin_roi_pct:string|null;reason:string};
export function priceReturnDisplay(result?:PriceResult){
 const missing={text:'未提供',tone:''};
 if(result?.status!=='AVAILABLE'||typeof result.price_return_pct!=='string'||!result.price_return_pct.trim())return missing;
 try{
  const value=new Decimal(result.price_return_pct);
  if(!value.isFinite())return missing;
  const zero=value.isZero();
  return {text:(value.isPositive()&&!zero?'+':'')+value.toFixed(4)+'%',tone:zero?'':value.isPositive()?'positive':'negative'};
 }catch{return missing;}
}
export function executionReturnMarkers(markers:Marker[],result?:PriceResult){
 const label=priceReturnDisplay(result);
 if(!label.tone&&label.text==='未提供')return markers;
 return markers.map(m=>m.action==='CLOSE'?{...m,text:`${m.text} · 價格報酬率（未扣交易成本） ${label.text}`}:m);
}
export function TradeReturnSummary({result}:{result?:PriceResult}){
 const label=priceReturnDisplay(result);
 return <span className="case-return-summary">價格報酬率（未扣交易成本） <strong className={label.tone}>{label.text}</strong></span>;
}
export default function TradeResult({result}:{result?:PriceResult}){
 if(!result||result.status!=='AVAILABLE')return <p>單筆價格結果資料不足。</p>;
 const label=priceReturnDisplay(result);
 return <dl className="cw-operation-values"><div><dt>原單進場 → 平倉</dt><dd>{result.entry_price??'—'} → {result.exit_price??'—'}</dd></div><div><dt>方向調整價差／盎司</dt><dd>{result.move_per_oz} USD</dd></div><div><dt>價格報酬率（未扣交易成本）</dt><dd className={label.tone}>{label.text}</dd></div><div><dt>保證金 ROI</dt><dd>缺單筆資金基準</dd></div></dl>;
}
