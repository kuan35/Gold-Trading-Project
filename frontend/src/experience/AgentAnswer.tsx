import {useState,type ComponentProps} from 'react';
import ConversationReply,{compactReplySections,AnswerSection} from '../ConversationReply';
import {analysisLabel,isModelAnalysis} from '../assistantProvider';import {selectionLabel} from '../modelSettings';
import {trendSignals} from '../discussionPanels';import NoCaseReasons from '../NoCaseReasons';
import DraftScenarioRisk from '../DraftScenarioRisk';import {asksVolume} from '../LiveVolumeAnalysis';
import TradeAdviceCard from '../TradeAdviceCard';
import CasePerformance from '../CasePerformance';
import {oldRevision} from '../caseOutcomes';
import {agentSummarySections,summaryEvidenceNote} from '../agentSummary';

export default function AgentAnswer(props:ComponentProps<typeof ConversationReply>){
 const {reply:r,onChart,question='',currentRevision}=props;const [open,setOpen]=useState(false);
 if(r.llm_status==='market_unavailable')return <article className="ag-insight">
  <header><span className="ag-chip ag-chip-soft">盤面暫未就緒</span></header>
  <p role="status">{r.message||'行情尚未就緒，請稍後再更新盤面。'}</p>
 </article>;
 const modelAnalysis=isModelAnalysis(r.provider);
 const checkedByAgent=modelAnalysis&&r.analysis_mode==='draft_snapshot'&&question==='檢查目前委託';
 const consolidated=modelAnalysis&&(checkedByAgent||Boolean(r.trade_advice));
 if(r.market_status==='INFORMATION'||r.analysis_mode==='gold_knowledge'||r.analysis_mode==='macro_events'||(!consolidated&&asksVolume(question)))return <div className="ag-insight"><ConversationReply {...props}/></div>;
 const c=r.case_comparison,first=c?.cases[0],p=first?.representative;
 const side=c?.side==='BUY'||c?.side==='SELL'?c.side:null,signals=trendSignals(r,side);
 const sections=compactReplySections(r,question);
 // Repaired numerical ledgers belong in details, not a large clipped headline.
 const narrative=(consolidated?r.sections:sections).filter(s=>s.source!=='program');
 const performance=c?.performance?.status==='AVAILABLE'?c.performance:null;
 const story=!performance&&narrative.find((s,i)=>i>0&&s.fact_ids.includes('history.trade1'));
 const primary=consolidated?[...agentSummarySections(r),...(story?[story]:[])]:narrative.length?narrative:sections;
 const history=r.evidence.find(f=>f.id==='history.trade1')?.values;
 const storyHasTradeFacts=history&&primary.some(s=>s.fact_ids.includes('history.trade1')&&
  [history.hist1_entry,history.hist1_exit,history.hist1_price_return,history.hist1_opened_day??history.hist1_opened_at].every(v=>v&&s.text.includes(v)));
 const showHistoryFacts=modelAnalysis&&history&&!storyHasTradeFacts&&
  (history.hist1_opened_day||history.hist1_opened_at)&&history.hist1_entry&&history.hist1_exit&&history.hist1_price_return;
 const count=(v:unknown)=>typeof v==='number'&&Number.isSafeInteger(v)&&v>=0?v:null;
 const matches=count(c?.counts.passed),pairs=count(r.trade_advice?.simulations?.count);
 const sampleNote=matches!==null?`相似案例：${matches} 組${pairs!==null&&pairs!==matches?`；多空試算參考 ${pairs} 組歷史盤面`:''}`:
  pairs!==null?`多空試算參考 ${pairs} 組相似盤面`:null;
 return <article className="ag-insight"><header><span className="ag-chip ag-chip-soft">{analysisLabel(r.provider)}{r.model&&modelAnalysis?` · ${selectionLabel(r.model,r.requested_effort)}`:''}{modelAnalysis&&r.llm_status==='partial_grounding'?(r.summary_evidence_state==='INCOMPLETE_HISTORY'?' · 歷史關聯未完成':' · 部分段落已篩除'):''}</span><time>{new Date(r.as_of_utc).toLocaleTimeString('zh-TW',{hour12:false})}</time></header>
  {r.llm_status==='invalid_grounding'&&<p role="status">這則 AI 回覆未通過資料引用或數值檢查，以下是程式摘要。</p>}
  {!consolidated&&r.trade_advice&&<TradeAdviceCard advice={r.trade_advice} staleDraft={Boolean(r.outcome_analysis&&oldRevision(r.outcome_analysis,currentRevision))} onChart={r.snapshot_id?()=>onChart('analysis','5m'):undefined}/>}
  {r.analysis_history_error&&<p role="status">{r.analysis_history_error}</p>}
  {!['CURRENT','FROZEN'].includes(r.market_status)&&<p role="status">{r.message||'行情尚未就緒，無法判讀完整盤面。'}</p>}
  <div className="ag-answer-prose">{primary.map((s,i)=><AnswerSection key={i} section={s}/>)}</div>
  {summaryEvidenceNote(r)&&<p role="status" className="fine">{summaryEvidenceNote(r)}</p>}
  {performance&&<CasePerformance data={performance}/>}
  {!performance&&showHistoryFacts&&<section className="ag-case-preview" aria-label="歷史原單操作參照">
   <strong>歷史操作參照</strong>
   <p>{history.hist1_opened_day??history.hist1_opened_at} · {history.hist1_side_state} {history.hist1_entry} → {history.hist1_exit} 平倉{history.hist1_closed_day&&`（${history.hist1_closed_day}）`}</p>
   <p>原單價格報酬 <strong>{history.hist1_price_return}%</strong>（未扣交易成本）{history.hist1_report_profit&&` · 原報表損益 ${history.hist1_report_profit} ${history.hist1_currency??'幣別未載'}`}</p>
  </section>}
  {!consolidated&&<>
  {(signals.support.length>0||signals.against.length>0)&&<div className="ag-signals">{signals.support.map(s=><span key={s.factId} className="ag-chip ag-chip-up">支持 · {s.period} · {s.text}</span>)}{signals.against.map(s=><span key={s.factId} className="ag-chip ag-chip-down">相反 · {s.period} · {s.text}</span>)}</div>}
  {c&&!first&&<NoCaseReasons comparison={c} compact/>}
  {!performance&&first&&<section className="ag-case-preview"><strong>{first.ref} · {first.event}</strong><p>{first.similarities[0]??'相同操作方向'}</p>{first.differences[0]&&<p>差異：{first.differences[0]}</p>}<p>代表單筆原報表結果：<strong className={p?.result==='WIN'?'positive':p?.result==='LOSS'?'negative':''}>{p?.profit??'未提供'}</strong> {p?.currency_stated?p.currency:'幣別未載'}</p></section>}
  {r.outcome_analysis&&(r.outcome_analysis.draft_risk.side||/草稿|風險|停損|停利/.test(question))&&<DraftScenarioRisk analysis={r.outcome_analysis} currentRevision={currentRevision}/>}
  </>}
  {sampleNote&&<p className="ag-case-count" aria-label="本次建議的案例數">{sampleNote}</p>}
  <div className="ag-details-actions">{r.snapshot_id&&<button type="button" className="ag-ghost" onClick={()=>onChart('analysis','5m')}>看圖</button>}{first&&r.snapshot_id&&<button type="button" className="ag-ghost" onClick={()=>onChart('cases')}>查看 K 線證據</button>}</div>
  <button type="button" className="ag-expand" aria-expanded={open} onClick={()=>setOpen(v=>!v)}>{open?'收合完整分析':'展開完整分析與案例'}<span className={open?'ag-rot':''}>⌄</span></button>
  {open&&<div className="ag-detail">
   {consolidated&&narrative.filter(s=>!primary.includes(s)).map((section,i)=><AnswerSection key={i} section={section}/>)}
   <ConversationReply {...props} showTradeAdvice={consolidated} showSummary={!consolidated}/>
  </div>}
 </article>;
}
