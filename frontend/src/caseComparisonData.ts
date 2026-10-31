import type {PriceResult} from './TradeResult';
import type {HoldingObservationData} from './HoldingObservation';
import type {Bar,Marker} from './types';
import type {OutcomeHorizon,Scenario} from './caseOutcomes';
export type Candle=Omit<Bar,'volume'>;
export type ExecutionCoverage={scope:'WHOLE_REFERENCE_HOLDING'|'ENDPOINT_WINDOWS';calendar_slots:number;available_bars:number;gap_slots:number};
export type ComparisonCharts={snapshot_id:string;query_as_of_utc:number|null;query:Record<'5m'|'1h',Candle[]>;cases:({ref:string;as_of_utc:number|null;holding_observation?:HoldingObservationData;execution?:{status:string;reason:string;mode?:string;coverage?:ExecutionCoverage;bars:Candle[];close_bars:Candle[];markers:Marker[];result?:PriceResult}|null}&Record<'5m'|'1h',Candle[]>)[]};
export type HorizonMinutes=5|30|60;
export type ComparisonSelection={caseRef:string;minutes:HorizonMinutes};
export type ExpandedOutcome={snapshot_id:string;case_ref:string;history:OutcomeHorizon&{anchor_price:string|null;bars:Candle[]};scenario:Scenario};
export function matchingOutcome(response:{snapshot_id:string;case_ref:string;history:{minutes:number}},snapshotId:string,caseRef:string,minutes:number){
 return response.snapshot_id===snapshotId&&response.case_ref===caseRef&&response.history.minutes===minutes;
}
// Display only: no resampling, no interpolation, no changes to retrieval inputs.
export function historicalDisplay(before:Candle[],history?:{status:string;anchor_time?:number|null;bars:Candle[]}){
 const unchanged={bars:before,markers:[] as Marker[],futureCount:0};
 if(history?.status!=='AVAILABLE'||typeof history.anchor_time!=='number'||!before.length||!history.bars.length)return unchanged;
 if(before[before.length-1].time>=history.anchor_time||history.bars[0].time!==history.anchor_time)return unchanged;
 if(history.bars.some((b,i)=>b.time!==history.anchor_time!+i*300||!['open','high','low','close'].every(k=>Number.isFinite(b[k as keyof Candle]))))return unchanged;
 return {bars:[...before,...history.bars],futureCount:history.bars.length,markers:[{time:history.anchor_time,position:'aboveBar',color:'#e6bb76',shape:'circle',text:'歷史後續起點'}] as Marker[]};
}
