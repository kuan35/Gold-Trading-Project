import Decimal from 'decimal.js';
import type {Retrieval} from './types';

export function comparisonValue(value:string|null|undefined):string{
 if(value==null)return '資料不足';
 try{const n=new Decimal(value);return n.isFinite()?n.toFixed(3).replace(/\.?0+$/,'')||'0':'資料不足';}
 catch{return '資料不足';}
}

export function poolDescription(pool:Retrieval):{operation:string;market:string;reason:string}{
 const c=pool.comparison,strict=c?.mode==='market_and_operation';
 return {
  operation:`${c?.operation_candidates??pool.total} 個操作條件候選群；首筆主要比較方向、可見首筆與手數。`,
  market:strict?(pool.total?`${pool.total} 個案例同時通過操作與盤面門檻`:'沒有同時通過操作與盤面條件的案例'):'盤面尚無法比較；以下案例僅供操作條件參考',
  reason:c?.reason||'目前未使用歷史盤面特徵，不等於K線相似。',
 };
}
