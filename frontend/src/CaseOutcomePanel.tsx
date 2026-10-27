import {useEffect,useState} from 'react';import ConversationCharts from './ConversationCharts';import OutcomeSummary from './OutcomeSummary';
import type {OutcomeAnalysis} from './caseOutcomes';import {oldRevision} from './caseOutcomes';import type {ComparisonSelection,HorizonMinutes} from './caseComparisonData';
export default function CaseOutcomePanel({analysis,snapshotId,light=false,currentRevision,onCompare}:{analysis:OutcomeAnalysis;snapshotId:string|null;light?:boolean;currentRevision?:number;onCompare?:(selection:ComparisonSelection)=>void}){
 const [index,setIndex]=useState(0),[minutes,setMinutes]=useState<HorizonMinutes>(60),[opened,setOpened]=useState(false);
 const item=analysis.cases[index],h=item?.horizons[String(minutes)],scenario=item?.scenarios[String(minutes)],stale=oldRevision(analysis,currentRevision);
 useEffect(()=>{setIndex(0);setMinutes(60);setOpened(false);},[snapshotId]);
 if(!item)return null;
 return <section className="case-outcomes" aria-label="歷史後續走勢與情境損失"><header><h3>歷史後續與情境損失</h3><span>歷史觀察 · 非預測</span></header>
  <div className="scenario-controls">{analysis.cases.length>1?<label>案例<select value={index} onChange={e=>setIndex(Number(e.target.value))}>{analysis.cases.map((c,i)=><option key={c.ref} value={i}>{c.ref}</option>)}</select></label>:<strong>{item.ref}</strong>}
   <div role="group" aria-label="固定後續觀察期間">{([5,30,60] as const).map(n=><button type="button" key={n} aria-pressed={minutes===n} onClick={()=>setMinutes(n)}>{n===60?'1 小時':n+' 分鐘'}</button>)}</div>
  </div>
  <OutcomeSummary history={h??{status:'MISSING',reason:'原快照沒有這個期間，請重新提問。',minutes,change_pct:null,mae_pct:null,mfe_pct:null}} scenario={scenario} stale={stale}/>
  <button type="button" disabled={!snapshotId} aria-expanded={onCompare?undefined:opened} onClick={()=>onCompare?onCompare({caseRef:item.ref,minutes}):setOpened(v=>!v)}>{!onCompare&&opened?'收合進場前與後續對照':'查看進場前與後續對照'}</button>
  {opened&&snapshotId&&!onCompare&&<ConversationCharts key={snapshotId+item.ref+minutes} snapshotId={snapshotId} mode="cases" light={light} selection={{caseRef:item.ref,minutes}} onClose={()=>setOpened(false)}/>}
  <details><summary>觀察範圍</summary><p className="fine">完整匹配池 {analysis.matched_cases??'未知'} 例，本區只呈現選出的 {analysis.displayed_cases} 例。後續從參考進場後首根完整五分棒開盤起算，不是交易員實際成交價；情境損失未套停損退出、不含成本。原始時鐘未獨立核實。</p></details>
 </section>;
}
