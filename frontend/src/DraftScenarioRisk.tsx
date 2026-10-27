import type {OutcomeAnalysis} from './caseOutcomes';import {oldRevision} from './caseOutcomes';
export default function DraftScenarioRisk({analysis,currentRevision}:{analysis:OutcomeAnalysis;currentRevision?:number}){
 const r=analysis.draft_risk,stale=oldRevision(analysis,currentRevision);
 return <section className="case-draft-risk" aria-label="本筆草稿風險檢查"><header><h3>本筆草稿風險</h3><span>{stale?'原分析草稿':'分析時草稿'}</span></header>
  {stale&&<p className="scenario-warning" role="status">欄位已變更，以下是原草稿風險；請重新檢查委託。</p>}
  {r.status==='AVAILABLE'?<><dl className="scenario-metrics"><div><dt>擬進場價</dt><dd>{r.entry_price}</dd></div><div><dt>新增手數</dt><dd>{r.side==='BUY'?'做多':'做空'} {r.lot} 手</dd></div><div><dt>停損名目損失</dt><dd>{r.stop_loss_usd===null?'未設定停損':r.stop_loss_usd+' USD'}</dd></div></dl>
   {r.conditional_on_fill&&<p className="fine">限價情境假設指定價格已成交，不代表委託能成交。</p>}
   {!analysis.cases.length&&<p>本次沒有可用的歷史情境，仍可核對這筆草稿的停損與損失。</p>}
   <details><summary>計算範圍</summary><p className="fine">只計新增本筆，使用券商合約單位。未包含既有倉位、價差、佣金、隔夜費、滑價或保證金；停損金額是距離試算，不是損失上限保證。</p></details>
  </>:<p className="scenario-empty">{r.reason}</p>}
 </section>;
}
