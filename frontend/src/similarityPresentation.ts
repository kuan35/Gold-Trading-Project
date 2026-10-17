import Decimal from 'decimal.js';
import type {Retrieval} from './types';

export function comparisonValue(value:string|null|undefined):string{
 if(value==null)return '資料不足';
 try{const n=new Decimal(value);return n.isFinite()?n.toFixed(3).replace(/\.?0+$/,'')||'0':'資料不足';}
 catch{return '資料不足';}
}

export function poolDescription(pool:Retrieval):{operation:string;market:string;reason:string}{
 const c=pool.comparison,strict=c?.mode==='market_and_operation';
 if(c?.mode==='candidate_market')return {
  operation:'只篩買進／賣出方向；手數、首筆或加倉、事後盈虧均不參與排序。',
  market:pool.candidate_market_unavailable_reason?'候選盤面暫無法比較':`候選盤面 · 完整三週期 ${pool.total} 群／五分鐘限定 ${pool.five_minute_only_total??0} 群`,
  reason:c.reason||'券商時鐘未核實；兩軸相對排名只用於候選檢索。',
 };
 if(c?.basis==='direction_only'&&!strict)return {operation:`${c.operation_candidates??pool.total} 個合成案例依買賣方向列出；不比較手數。`,
  market:'盤面無法比較',reason:c.reason||'合成案例沒有歷史盤面。'};
 return {
  operation:`${c?.operation_candidates??pool.total} 個操作條件候選群；首筆主要比較方向、可見首筆與手數。`,
  market:strict?(pool.total?`${pool.total} 個案例同時通過操作與盤面門檻`:'沒有同時通過操作與盤面條件的案例'):'盤面尚無法比較；以下案例僅供操作條件參考',
  reason:c?.reason||'目前未使用歷史盤面特徵，不等於K線相似。',
 };
}
