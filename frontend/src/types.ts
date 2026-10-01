export type Side = 'BUY' | 'SELL';
export type Action = 'FIRST' | 'ADD' | 'OPPOSITE';
export type Bar = {time:number;open:number;high:number;low:number;close:number;volume:number};
export type Marker = {time:number;position:'belowBar'|'aboveBar';color:string;shape:'arrowUp'|'arrowDown'|'circle';text:string};
export type Position = {id:string;side:Side;lot:string;entry:string;sl:string|null;tp:string|null;pnl:string;opened_at:string|number};
export type Order = {id:string;side:Side;lot:string;price:string;status:string;time:string|number;action:string;pnl?:string|null};
export type State = {mode:'replay'|'broker_demo';version:number;clock:string|number;data_source:string;broker_connected:boolean;llm_enabled:boolean;quote:{bid:string;ask:string;time:string|number};account:{balance:string;equity:string};positions:Position[];orders:Order[];market:{change_pct:string;range_pct:string;high:string;low:string;ma20:string|null;ma60:string|null};data_quality:string[]};
export type Case = {id:string;label:string;side:Side;action:Action;lot:string;entry:string;exit:string;opened_at:string|number;closed_at:string;profit:string;currency?:string;distance:string|number|null;match_reasons:string[];differences:string[];group:string;source_kind:'synthetic_demo'|'trader_history';time_alignment:'confirmed'|'unknown';behavior:string;sequence_total?:number;sequence:{index:number;ordering_uncertain?:boolean;side:Side;lot:string;entry:string;exit:string;profit:string;role:string}[];bars?:Bar[];markers?:Marker[];chart_unavailable_reason?:string;chart_reason?:string};
export type Retrieval = {total:number;wins:number;losses:number;flat:number;unknown:number;win_rate:string|null;cases:Case[];limitations:string[]};
export type Draft = {id:string;revision:number;side:Side;lot:string;sl:string|null;tp:string|null;price:string;action:Action;status:string;risk:{before_lot:string;after_lot:string;average_entry:string;stop_loss_usd:string|null;reward_risk:string|null;scenarios:{move:string;loss:string}[];warnings:string[]};retrieval:Retrieval;explanation:string};
export type Audit = {source_files:number;total_gold_records:number;period:string;groups:{code:string;label:string;count:number;description:string}[];limitations:string[];refreshed_at:string;source:string};
export type BarsResponse = {bars:Bar[];markers:Marker[];source:string;interval:string};


