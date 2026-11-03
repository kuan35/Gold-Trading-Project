import {useState,type ComponentProps} from 'react';
import ConversationReply,{compactReplySections,AnswerSection} from '../ConversationReply';
import {analysisLabel,isModelAnalysis} from '../assistantProvider';import {selectionLabel} from '../modelSettings';
import {trendSignals} from '../discussionPanels';import NoCaseReasons from '../NoCaseReasons';
import DraftScenarioRisk from '../DraftScenarioRisk';import {asksVolume} from '../LiveVolumeAnalysis';

export default function AgentAnswer(props:ComponentProps<typeof ConversationReply>){
 const {reply:r,onChart,question='',currentRevision}=props;const [open,setOpen]=useState(false);
 if(r.market_status==='INFORMATION'||r.analysis_mode==='gold_knowledge'||r.analysis_mode==='macro_events'||asksVolume(question))return <div className="ag-insight"><ConversationReply {...props}/></div>;
 const c=r.case_comparison,first=c?.cases[0],p=first?.representative;
 const side=c?.side==='BUY'||c?.side==='SELL'?c.side:null,signals=trendSignals(r,side);
 const sections=compactReplySections(r,question);
 // Repaired numerical ledgers belong in details, not a large clipped headline.
 const narrative=sections.filter(s=>s.source!=='program');
 const primary=narrative.length?narrative:sections;
 return <article className="ag-insight"><header><span className="ag-chip ag-chip-soft">{analysisLabel(r.provider)}{r.model&&isModelAnalysis(r.provider)?` · ${selectionLabel(r.model,r.requested_effort)}`:''}</span><time>{new Date(r.as_of_utc).toLocaleTimeString('zh-TW',{hour12:false})}</time></header>
  {r.analysis_history_error&&<p role="status">{r.analysis_history_error}</p>}
  {!['CURRENT','FROZEN'].includes(r.market_status)&&<p role="status">{r.message||'行情尚未就緒，無法判讀完整盤面。'}</p>}
  {c&&!first&&<NoCaseReasons comparison={c}/>}
  <div className="ag-answer-prose">{primary.map((s,i)=><AnswerSection key={i} section={s}/>)}</div>
  {(signals.support.length>0||signals.against.length>0)&&<div className="ag-signals">{signals.support.map(s=><span key={s.factId} className="ag-chip ag-chip-up">支持 · {s.period} · {s.text}</span>)}{signals.against.map(s=><span key={s.factId} className="ag-chip ag-chip-down">相反 · {s.period} · {s.text}</span>)}</div>}
  {c&&first&&<p className="ag-case-count">符合情境 {c.counts.passed??'—'} 群 · 合格觀察列 {c.counts.eligible??'—'}</p>}
  {first&&<section className="ag-case-preview"><strong>{first.ref} · {first.event}</strong><p>{first.similarities[0]??'相同操作方向'}</p>{first.differences[0]&&<p>差異：{first.differences[0]}</p>}<p>代表單筆原報表結果：<strong className={p?.result==='WIN'?'positive':p?.result==='LOSS'?'negative':''}>{p?.profit??'未提供'}</strong> {p?.currency_stated?p.currency:'幣別未載'}</p></section>}
  {r.outcome_analysis&&(r.outcome_analysis.draft_risk.side||/草稿|風險|停損|停利/.test(question))&&<DraftScenarioRisk analysis={r.outcome_analysis} currentRevision={currentRevision}/>}
  <div className="ag-details-actions">{r.snapshot_id&&<button type="button" className="ag-ghost" onClick={()=>onChart('analysis','5m')}>看圖</button>}{first&&r.snapshot_id&&<button type="button" className="ag-ghost" onClick={()=>onChart('cases')}>查看 K 線證據</button>}</div>
  <button type="button" className="ag-expand" aria-expanded={open} onClick={()=>setOpen(v=>!v)}>{open?'收合完整分析':'展開完整分析與案例'}<span className={open?'ag-rot':''}>⌄</span></button>
  {open&&<div className="ag-detail"><ConversationReply {...props}/></div>}
 </article>;
}
