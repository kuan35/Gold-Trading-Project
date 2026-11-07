import Decimal from 'decimal.js';
import type {Side} from './types';

export type AdviceMode = 'COMPARE' | 'SIDE';
export type RiskBudget = {mode:'usd'|'pct';value:string};
type SimulationStats = {median_pct:string|null;positive:number;better:number;stress_median_pct:string|null};
type OriginalStats = {count:number;median_pct:string|null;positive:number;negative:number};
export type TradeAdvice = {
 action:Side|'WAIT'|'ADJUST';
 side:Side|null;
 headline:string;
 reason:string;
 signal:string|null;
 direction?:{side:Side;basis:string;reason:string}|null;
 as_of:number|null;
 simulations:Record<Side,SimulationStats>&{count:number};
 original:Record<Side,OriginalStats>;
 costs:null|{baseline_usd_per_oz:string;stress_usd_per_oz:string};
 protection?:{
  status:'AVAILABLE'|'UNAVAILABLE';entry:string|null;stop:string|null;target:string|null;
  reward_risk_ratio:string|null;stop_basis:string|null;target_basis:string|null;
  reason:string|null;entry_basis:string;conditional:boolean;
 };
 draft:null|{
  stop_loss_usd:string|null;
  equity_pct:string|null;
  budget_usd:string|null;
  suggested_lot:string|null;
  scenario:null|{stop:number;target:number;ambiguous:number;expired:number;unknown:number};
 };
};

const long = '(?:做多|買進|買入|BUY)';
const short = '(?:做空|賣出|SELL)';
const buyWords=new RegExp(long,'i');
const sellWords=new RegExp(short,'i');
const direction=`(?:${long}|${short})`;
const compare = new RegExp(`${long}\\s*(?:還是|或是|或)\\s*${short}|${short}\\s*(?:還是|或是|或)\\s*${long}|買還是賣|賣還是買|比較(?:一下)?(?:做)?多(?:空|與空)|多空比較|比較.{0,8}(?:做多.{0,8}做空|做空.{0,8}做多)`, 'i');
const explicitSide = new RegExp(`(?:我(?:現在)?想|我打算|我考慮|建議|適合|可以|該不該|要不要|可不可以).{0,8}${direction}|${direction}.{0,4}(?:可以嗎|合適嗎|適合嗎|好嗎|可行嗎)|(?:如果|假如|若).{0,8}${direction}.{0,6}(?:會怎樣|會發生什麼|風險)`, 'i');

export function adviceMode(question:string, side?:Side|null):AdviceMode|undefined {
 if (question.trim()==='更新目前盤面與案例'||compare.test(question)) return 'COMPARE';
 if (side && explicitSide.test(question)) return 'SIDE';
}

export function adviceSide(question:string):Side|undefined {
 const hasBuy=buyWords.test(question);
 const hasSell=sellWords.test(question);
 if(hasBuy!==hasSell)return hasBuy?'BUY':'SELL';
}

export function riskBudgetFields(budget:RiskBudget):{risk_usd?:string;equity_pct?:string} {
 const value=budget.value.trim();
 if (!/^(?:\d+\.?\d*|\.\d+)$/.test(value) || value.length>30) return {};
 const number=new Decimal(value);
 if (!number.isFinite() || number.lte(0) || (budget.mode==='pct' && number.gt(100))) return {};
 return budget.mode==='usd'?{risk_usd:value}:{equity_pct:value};
}

const pct=(value:string|null)=>value===null?'資料不足':new Decimal(value).toSignificantDigits(5).toFixed()+'%';
const ratio=(positive:number,count:number)=>count?`${positive}／${count} 組`:'無可比較組';

export function adviceRows(advice:TradeAdvice) {
 const {simulations,original}=advice;
 return (['BUY','SELL'] as const).map(side=>({
  side,
  label:side==='BUY'?'做多':'做空',
  simulation:advice.costs?`${pct(simulations[side].median_pct)} · 正報酬 ${ratio(simulations[side].positive,simulations.count)}`:'等待成本設定',
  stress:pct(simulations[side].stress_median_pct),
  original:`${pct(original[side].median_pct)} · 正報酬 ${ratio(original[side].positive,original[side].count)}`,
 }));
}

export function adviceDraftDetails(draft:TradeAdvice['draft']):string[] {
 if(!draft) return [];
 const {scenario}=draft;
 return [
  draft.stop_loss_usd===null?'停損情境損失資料不足':`停損情境損失 ${draft.stop_loss_usd} USD${draft.equity_pct===null?'':` · 淨值 ${draft.equity_pct}%`}`,
  draft.budget_usd===null?'請依可承擔的損失設定風險預算。':`風險預算 ${draft.budget_usd} USD`,
  ...(draft.suggested_lot===null?[]:[`可試算調整至 ${draft.suggested_lot} 手`]),
  ...(scenario?[`假設已進場，30 分鐘內先觸停損 ${scenario.stop} 組、先觸停利 ${scenario.target} 組、順序未知 ${scenario.ambiguous} 組、到期 ${scenario.expired} 組、資料不足 ${scenario.unknown} 組。`]:[]),
 ];
}
