import Decimal from 'decimal.js';
export type DraftRisk={status:string;reason:string;scope:string;side?:string|null;lot?:string|null;order_type?:string|null;entry_price?:string|null;quantity_oz?:string|null;stop_price?:string|null;target_price?:string|null;stop_loss_usd:string|null;conditional_on_fill:boolean;assumption?:string};
export type OutcomeHorizon={status:string;reason:string;minutes:number;change_pct:string|null;mae_pct:string|null;mfe_pct:string|null;anchor_time?:number|null;end_time?:number|null;source?:string};
export type Scenario={status:string;reason?:string;mae_loss_usd:string|null;end_pnl_usd:string|null;mfe_profit_usd?:string|null;touch_label?:string;touch_state?:string;gap_at_first_touch?:boolean;first_touch_minutes?:number|null;conditional_on_fill?:boolean};
export type OutcomeAnalysis={status:string;draft_risk:DraftRisk;input_revision:number|null;matched_cases:number|null;displayed_cases:number;cases:{ref:string;horizons:Record<string,OutcomeHorizon>;scenarios:Record<string,Scenario>}[]};
export const percent=(value:string|null|undefined)=>{if(value===null||value===undefined)return '資料不足';try{const d=new Decimal(value);return d.isFinite()?d.toFixed(3)+'%':'資料不足';}catch{return '資料不足';}};
export const oldRevision=(analysis:OutcomeAnalysis,current?:number)=>current!==undefined&&analysis.input_revision!==null&&analysis.input_revision!==current;
