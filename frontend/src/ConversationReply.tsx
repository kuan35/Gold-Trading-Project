import {useId,useState} from 'react';
import LiveVolumeAnalysis,{asksVolume} from './LiveVolumeAnalysis';
import type {MarketReply} from './LiveAssistant';import CaseComparison from './CaseComparison';
import CaseOperations,{operationLabel} from './CaseOperations';
export function compactSections(sections:MarketReply['sections']){
 const first=sections[0],hour=sections.find(s=>s!==first&&s.fact_ids.some(id=>id.startsWith('f1.')));
 return first?[first,...(hour?[hour]:sections.slice(1,2))]:[];
}
const factText=(f:MarketReply['evidence'][number])=>f.text.replace(/\{\{([a-z0-9_]+)\}\}/g,(_,k)=>f.values[k]??'資料不足');
export function compactReplySections(r:MarketReply,question=''):MarketReply['sections']{
 if(r.provider==='groq_market_analysis')return compactSections(r.sections.filter(s=>s.fact_ids.some(id=>id!=='limits'&&!id.startsWith('history.'))));
 const frames=r.sections.filter(s=>s.fact_ids.some(id=>/^f(5|15|1)\./.test(id)));
 const axis=/支撐|壓力|前高|前低/.test(question)?'levels':/RSI|MACD|動能/i.test(question)?'momentum':/波動|ATR/i.test(question)?'range':'trend';
 const chosen=compactSections(frames);
 return chosen.length?chosen.map(s=>{
  const f=r.evidence.find(f=>s.fact_ids.includes(f.id)&&f.id.endsWith('.'+axis))??r.evidence.find(f=>s.fact_ids.includes(f.id)&&f.id.endsWith('.trend'))??r.evidence.find(f=>s.fact_ids.includes(f.id));
  if(!f)return s;
  const prefix=f.id.split('.')[0],v=f.values;
  const levelText=f.id.endsWith('.levels')&&v[prefix+'_support']&&v[prefix+'_resistance']?`下方參考：${v[prefix+'_support']}；上方參考：${v[prefix+'_resistance']}。`:null;
  const text=levelText??(f.id.endsWith('.trend')&&v[prefix+'_bias']&&v[prefix+'_live_structure']?`${v[prefix+'_bias']}（已收棒）。${v[prefix+'_live_structure'].replace('；均線仍以已收棒計算。','。')}`:factText(f));
  return {...s,text,fact_ids:[f.id]};
 }):compactSections(r.sections);
}
function AnswerSection({section:s,onChart}:{section:MarketReply['sections'][number];onChart?:()=>void}){
 const [expanded,setExpanded]=useState(false),id=useId(),long=s.text.length>170;
 return <section className="cw-answer-section"><h3>{s.title}</h3><p id={id} className={long&&!expanded?'cw-answer-preview':undefined}>{s.text}</p><div className="cw-answer-actions">{long&&<button type="button" aria-expanded={expanded} aria-controls={id} onClick={()=>setExpanded(!expanded)}>{expanded?'收合這段':'展開這段'}</button>}{onChart&&<button type="button" className="cw-point-link" onClick={onChart}>看圖</button>}</div></section>;
}
export default function ConversationReply({reply:r,onChart,question=''}:{reply:MarketReply;onChart:(mode:'analysis'|'cases',period?:'5m'|'15m'|'1h')=>void;question?:string}){
 const c=r.case_comparison,first=c?.cases[0],p=first?.representative,displayed=asksVolume(question)&&!/趨勢|走勢|RSI|MACD|支撐|壓力|波動|ATR/i.test(question)&&r.provider!=='groq_market_analysis'?[]:compactReplySections(r,question);
 const provider=r.provider==='groq_market_analysis'?(r.llm_status==='partial_grounding'?'Groq＋程式':'Groq'):'程式解讀';
 return <article className="cw-reply"><header><strong>盤面重點</strong><small>{new Date(r.as_of_utc).toLocaleTimeString('zh-TW',{hour12:false})} · {provider}</small></header>
  {r.market_status!=='CURRENT'&&r.market_status!=='FROZEN'&&<p role="status">{r.message||'行情尚未就緒，此次無法判讀完整盤面。'}</p>}
  {displayed.map((s,i)=><AnswerSection key={i} section={s} onChart={r.snapshot_id&&s.fact_ids.some(id=>/^f(5|15|1)\./.test(id))?()=>onChart('analysis',s.fact_ids.some(id=>id.startsWith('f1.'))?'1h':s.fact_ids.some(id=>id.startsWith('f15.'))?'15m':'5m'):undefined}/>)}
  <LiveVolumeAnalysis reply={r} question={question}/>
  {c&&(first||['CURRENT','FROZEN'].includes(r.market_status))&&<section className="cw-case"><h3>{first?'最接近的歷史案例':c.label}</h3>{first?<><p>{c.side==='BUY'?'做多':'做空'} · {first.event} · {operationLabel(p?.action)}</p><p className={p?.result==='LOSS'?'negative':p?.result==='WIN'?'positive':''}>代表單筆原報表結果：<strong>{p?.profit??'未提供'}</strong> {p?.currency_stated?p.currency:'幣別未載'}</p><button type="button" onClick={()=>onChart('cases')}>看 K 線對照</button><CaseOperations snapshotId={r.snapshot_id??null} caseRef={first.ref}/></>:<p>{c.reason}</p>}
  </section>}
  <details className="cw-answer-evidence"><summary>詳細依據{first?' · 案例差異與歷史分布':''}</summary>
   <p className="fine">分析時間：{new Date(r.as_of_utc).toLocaleString('zh-TW',{hour12:false})}。本次回答與案例保留原快照。</p>
   {r.llm_status!=='ok'&&r.llm_status!=='disabled'&&<p>{r.provider==='groq_market_analysis'?'部分內容由程式補充。':'目前使用程式摘要；Groq 暫未提供完整解讀。'}</p>}
   {r.sections.map((s,i)=><section key={i}><h3>{s.title}</h3><p>{s.text}</p></section>)}
   {!!r.evidence.length&&<details><summary>逐項數據</summary>{r.evidence.map(f=><p key={f.id}>{factText(f)}</p>)}</details>}
   {c&&<>{c.distribution&&<p>{c.distribution.basis}：{c.distribution.total??'未知'} 群；獲利 {c.distribution.wins??'未知'}／虧損 {c.distribution.losses??'未知'}／持平 {c.distribution.flat??'未知'}／未知 {c.distribution.unknown??'未知'}。</p>}<CaseComparison comparison={c} snapshotId={r.snapshot_id??null} hideCharts/></>}
  </details>
 </article>;
}
