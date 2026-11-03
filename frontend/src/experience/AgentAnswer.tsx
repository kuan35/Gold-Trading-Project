import {useState,type ComponentProps} from 'react';
import ConversationReply,{compactReplySections} from '../ConversationReply';
import {analysisLabel,isModelAnalysis} from '../assistantProvider';import {selectionLabel} from '../modelSettings';
import {trendSignals} from '../discussionPanels';import NoCaseReasons from '../NoCaseReasons';
import DraftScenarioRisk from '../DraftScenarioRisk';import {asksVolume} from '../LiveVolumeAnalysis';

export default function AgentAnswer(props:ComponentProps<typeof ConversationReply>){
 const {reply:r,onChart,question='',currentRevision}=props;const [open,setOpen]=useState(false);
 if(r.market_status==='INFORMATION'||r.analysis_mode==='gold_knowledge'||r.analysis_mode==='macro_events'||asksVolume(question))return <div className="ag-insight"><ConversationReply {...props}/></div>;
 const c=r.case_comparison,first=c?.cases[0],p=first?.representative;
 const side=c?.side==='BUY'||c?.side==='SELL'?c.side:null,signals=trendSignals(r,side);
 const sections=compactReplySections(r,question),headline=sections[0]?.text??r.message??'盤面資料尚未就緒';
 return <article className="ag-insight"><header><span className="ag-chip ag-chip-soft">{analysisLabel(r.provider)}{r.model&&isModelAnalysis(r.provider)?` · ${selectionLabel(r.model,r.requested_effort)}`:''}</span><time>{new Date(r.as_of_utc).toLocaleTimeString('zh-TW',{hour12:false})}</time></header>
  {r.analysis_history_error&&<p role="status">{r.analysis_history_error}</p>}
  {!['CURRENT','FROZEN'].includes(r.market_status)&&<p role="status">{r.message||'行情尚未就緒，無法判讀完整盤面。'}</p>}
  {c&&!first&&<NoCaseReasons comparison={c}/>}
  <h3 className="ag-headline">{headline.length>180?headline.slice(0,180)+'…':headline}</h3>
  {(signals.support.length>0||signals.against.length>0)&&<div className="ag-signals">{signals.support.map(s=><span key={s.factId} className="ag-chip ag-chip-up">支持 · {s.period} · {s.text}</span>)}{signals.against.map(s=><span key={s.factId} className="ag-chip ag-chip-down">相反 · {s.period} · {s.text}</span>)}</div>}
  <div className="ag-tiles">{c&&<div className="ag-tile"><small>符合情境案例</small><strong>{c.counts.passed??'—'} 群</strong><span>合格觀察列 {c.counts.eligible??'—'}</span></div>}{sections[1]&&<div className="ag-tile"><small>{sections[1].title}</small><p>{sections[1].text.length>150?sections[1].text.slice(0,150)+'…':sections[1].text}</p></div>}</div>
  {first&&<section className="ag-case-preview"><strong>{first.ref} · {first.event}</strong><p>{first.similarities[0]??'相同操作方向'}</p>{first.differences[0]&&<p>差異：{first.differences[0]}</p>}<p>代表單筆原報表結果：<strong className={p?.result==='WIN'?'positive':p?.result==='LOSS'?'negative':''}>{p?.profit??'未提供'}</strong> {p?.currency_stated?p.currency:'幣別未載'}</p></section>}
  {r.outcome_analysis&&<DraftScenarioRisk analysis={r.outcome_analysis} currentRevision={currentRevision}/>}
  <div className="ag-details-actions">{r.snapshot_id&&<button type="button" className="ag-ghost" onClick={()=>onChart('analysis','5m')}>看圖</button>}{first&&r.snapshot_id&&<button type="button" className="ag-ghost" onClick={()=>onChart('cases')}>查看 K 線證據</button>}</div>
  <button type="button" className="ag-expand" aria-expanded={open} onClick={()=>setOpen(v=>!v)}>{open?'收合完整分析':'展開完整分析與案例'}<span className={open?'ag-rot':''}>⌄</span></button>
  {open&&<div className="ag-detail"><ConversationReply {...props}/></div>}
 </article>;
}
