import {useState,type ComponentProps} from 'react';
import ConversationReply,{compactReplySections,AnswerSection} from '../ConversationReply';
import {analysisLabel,isModelAnalysis} from '../assistantProvider';import {selectionLabel} from '../modelSettings';
import {trendSignals} from '../discussionPanels';import NoCaseReasons from '../NoCaseReasons';
import DraftScenarioRisk from '../DraftScenarioRisk';import {asksVolume} from '../LiveVolumeAnalysis';
import TradeAdviceCard from '../TradeAdviceCard';
import {oldRevision} from '../caseOutcomes';

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
 const primary=consolidated?narrative.slice(0,1):narrative.length?narrative:sections;
 return <article className="ag-insight"><header><span className="ag-chip ag-chip-soft">{analysisLabel(r.provider)}{r.model&&modelAnalysis?` · ${selectionLabel(r.model,r.requested_effort)}`:''}{modelAnalysis&&r.llm_status==='partial_grounding'?' · 部分段落已篩除':''}</span><time>{new Date(r.as_of_utc).toLocaleTimeString('zh-TW',{hour12:false})}</time></header>
  {r.llm_status==='invalid_grounding'&&<p role="status">這則 AI 回覆未通過資料引用或數值檢查，以下是程式摘要。</p>}
  {!consolidated&&r.trade_advice&&<TradeAdviceCard advice={r.trade_advice} staleDraft={Boolean(r.outcome_analysis&&oldRevision(r.outcome_analysis,currentRevision))} onChart={r.snapshot_id?()=>onChart('analysis','5m'):undefined}/>}
  {r.analysis_history_error&&<p role="status">{r.analysis_history_error}</p>}
  {!['CURRENT','FROZEN'].includes(r.market_status)&&<p role="status">{r.message||'行情尚未就緒，無法判讀完整盤面。'}</p>}
  <div className="ag-answer-prose">{primary.map((s,i)=><AnswerSection key={i} section={s}/>)}</div>
  {!consolidated&&<>
  {(signals.support.length>0||signals.against.length>0)&&<div className="ag-signals">{signals.support.map(s=><span key={s.factId} className="ag-chip ag-chip-up">支持 · {s.period} · {s.text}</span>)}{signals.against.map(s=><span key={s.factId} className="ag-chip ag-chip-down">相反 · {s.period} · {s.text}</span>)}</div>}
  {c&&!first&&<NoCaseReasons comparison={c} compact/>}
  {c&&first&&<p className="ag-case-count">符合情境 {c.counts.passed??'—'} 群 · 合格觀察列 {c.counts.eligible??'—'}</p>}
  {first&&<section className="ag-case-preview"><strong>{first.ref} · {first.event}</strong><p>{first.similarities[0]??'相同操作方向'}</p>{first.differences[0]&&<p>差異：{first.differences[0]}</p>}<p>代表單筆原報表結果：<strong className={p?.result==='WIN'?'positive':p?.result==='LOSS'?'negative':''}>{p?.profit??'未提供'}</strong> {p?.currency_stated?p.currency:'幣別未載'}</p></section>}
  {r.outcome_analysis&&(r.outcome_analysis.draft_risk.side||/草稿|風險|停損|停利/.test(question))&&<DraftScenarioRisk analysis={r.outcome_analysis} currentRevision={currentRevision}/>}
  </>}
  <div className="ag-details-actions">{r.snapshot_id&&<button type="button" className="ag-ghost" onClick={()=>onChart('analysis','5m')}>看圖</button>}{first&&r.snapshot_id&&<button type="button" className="ag-ghost" onClick={()=>onChart('cases')}>查看 K 線證據</button>}</div>
  <button type="button" className="ag-expand" aria-expanded={open} onClick={()=>setOpen(v=>!v)}>{open?'收合完整分析':'展開完整分析與案例'}<span className={open?'ag-rot':''}>⌄</span></button>
  {open&&<div className="ag-detail">
   {consolidated&&narrative.slice(1).map((section,i)=><AnswerSection key={i} section={section}/>)}
   <ConversationReply {...props} showTradeAdvice={consolidated} showSummary={!consolidated}/>
  </div>}
 </article>;
}
