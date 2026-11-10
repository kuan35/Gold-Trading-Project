import type {MarketReply} from './LiveAssistant';
import {isModelAnalysis} from './assistantProvider';
export type DraftAssessment={state:'pending'|'disabled'|'stale'|'error';error?:string}|{state:'ready';reply:MarketReply};
export function agentSummarySections(reply:MarketReply){
 if(!isModelAnalysis(reply.provider))return [];
 const sections=reply.sections.filter(s=>s.source!=='program');
 const first=sections[0];
 if(!first)return [];
 // Surface already-grounded model history prose, rather than hiding its
 // relationship to the plan beneath the local statistics card.
 const hasHistory=first.fact_ids.some(id=>id.startsWith('history.'));
 const history=sections.find(s=>s!==first&&s.fact_ids.some(id=>id==='history.aggregate')&&s.fact_ids.some(id=>/^history\.(case|shape|query_shape)/.test(id)));
 return [first,...(!hasHistory&&history?[history]:[])];
}
export function matchingAssessment(draft:{analysis_snapshot_id:string;analysis_as_of_utc:string},assessment?:DraftAssessment){
 if(assessment?.state!=='ready')return null;
 const reply=assessment.reply;
 return reply.snapshot_id===draft.analysis_snapshot_id&&reply.as_of_utc===draft.analysis_as_of_utc&&reply.market_status==='FROZEN'&&reply.analysis_mode==='draft_snapshot'&&isModelAnalysis(reply.provider)?reply:null;
}

export function summaryEvidenceNote(reply:MarketReply){return reply.summary_evidence_state==='INCOMPLETE_HISTORY'?'助手尚未完整說明歷史案例與本筆想法的關係；下方歷史統計由程式整理。':null;}
