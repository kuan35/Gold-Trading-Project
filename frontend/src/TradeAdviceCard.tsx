import {adviceDraftDetails,adviceRows,type TradeAdvice as TradeAdviceResult} from './tradeAdvice';

export default function TradeAdviceCard({advice,onChart,staleDraft=false}:{advice:TradeAdviceResult;onChart?:()=>void;staleDraft?:boolean}) {
 return <section className="trade-advice" aria-label="下單前建議">
  <h3>{advice.direction?(advice.direction.side==='BUY'?'方向偏多':'方向偏空'):advice.headline}</h3>
  {advice.direction&&<><p>{advice.direction.reason}</p><p><strong>進場判定 · {advice.headline}</strong></p></>}
  <p>{advice.reason}</p>
  {advice.signal&&<p>已收五分 K 訊號 · {advice.signal}</p>}
  {advice.protection&&<section className="trade-advice-draft" aria-label="停損停利建議">
   <h4>{advice.protection.conditional?'停損停利條件式參考':'停損停利建議'}</h4>
   {advice.protection.status==='AVAILABLE'?<>
    <p>進場基準 {advice.protection.entry} USD/oz · {advice.protection.entry_basis} · 預估報酬／風險 {advice.protection.reward_risk_ratio} 倍</p>
    <p><strong>建議停損 {advice.protection.stop}</strong> · {advice.protection.stop_basis}</p>
    <p><strong>建議停利 {advice.protection.target}</strong> · {advice.protection.target_basis}</p>
   </>:<p>{advice.protection.reason}</p>}
  </section>}
  <div className="trade-advice-evidence">
   {adviceRows(advice).map(row=><section key={row.side}>
    <h4>{row.label}</h4>
    <dl>
     <div><dt>同盤面 30 分鐘淨價格報酬中位數</dt><dd>{row.simulation}</dd></div>
     <div><dt>較高成本下的中位數</dt><dd>{row.stress}</dd></div>
     <div><dt>交易員原單價格報酬中位數（未扣成本）</dt><dd>{row.original}</dd></div>
    </dl>
   </section>)}
  </div>
  <details className="fine"><summary>什麼是一組完整配對？</summary><p>一組是一段去重後的歷史相似盤面，不是現在要下幾筆單。它要有完整的後續 30 分鐘，才能用同一進出時間和成本假設各試算一次做多、做空。</p><p>目前有1組完整資料即可納入建議，摘要後方標示實際案例數。盤面、成本與風險條件仍會檢查。相似案例數與有完整後續資料的多空試算數可能不同，會分別標示；少數歷史結果不當成這次勝率。完整統計與程式檢查仍在本區保留。</p></details>
  {advice.costs&&<p className="fine">同盤面試算往返成本假設 · 基準 {advice.costs.baseline_usd_per_oz} USD/oz · 較高 {advice.costs.stress_usd_per_oz} USD/oz</p>}
  {advice.draft&&<section className="trade-advice-draft">
   <h4>{staleDraft?'原分析草稿':'分析時草稿'}</h4>
   {staleDraft&&<p className="scenario-warning">欄位已變更，請重新檢查委託。</p>}
   {adviceDraftDetails(advice.draft).map(line=><p key={line}>{line}</p>)}
  </section>}
  {onChart&&<button type="button" className="ag-ghost" onClick={onChart}>查看訊號圖</button>}
 </section>;
}
