import {comparisonValue,poolDescription} from './similarityPresentation';
import type {Case,Retrieval} from './types';

export function PoolEvidence({pool}:{pool:Retrieval}){
 const text=poolDescription(pool),c=pool.comparison;
 return <section className="similarity-evidence" aria-label="相似案例比較範圍">
  <div className="similarity-axes"><div><span className="fine">操作條件</span><strong>{c?.basis==='relative_lot'?'比較相對平常手數':'比較絕對手數'}</strong><p>{text.operation}</p></div>
  <div><span className="fine">盤面條件</span><strong>{text.market}</strong><p>{text.reason}</p></div></div>
  {c?.verified_market_candidates!==undefined&&<p className="fine">同方向／操作類型中，有 {c.verified_market_candidates} 個已成熟案例具可用盤面資料；{c.excluded_unverified_market??0} 個尚無可用盤面資料。候選群不是獨立交易。</p>}
  <details><summary>如何判斷相似</summary><p>先篩方向、首筆／加倉與已成熟案例。操作距離上限0.65；有可用時間證據及完整盤面資料時，再比較5分／15分／1小時趨勢、相對位置與波動，盤面距離上限0.40。兩個門檻必須各自通過，再按操作40%、盤面60%排序。缺值保留懲罰，條件不符就不匹配。</p><p>權重與門檻是尚待相關性評測的工程設定；不是準確率、交易建議或預測勝率。盈虧只在匹配完成後分組展示。</p></details>
 </section>;
}

export function CaseEvidence({item}:{item:Case}){
 const op=item.operation_comparison,market=item.market_comparison;
 return <section className="similarity-evidence" aria-label="案例分項比對">
  <div className="similarity-axes"><div><span className="fine">操作條件</span><strong>{op?.label||'操作條件比較'}{op?.strength==='weak'?' · 辨識力有限':''}</strong><p>{op?.reason||'比較方向、首筆／加倉與手數等條件。'}</p><small>操作距離 {op?.distance??item.operation_distance??item.distance??'未提供'}（越小越接近）</small></div>
  <div><span className="fine">盤面條件</span><strong>{market?.label||'盤面尚無法比較'}</strong><p>{market?.reason||'尚無已核實時間的盤面比較證據。'}</p>{market?.status==='matched'&&<small>盤面距離 {market.distance} · 可比較欄位權重覆蓋 {Math.round(market.coverage*100)}%（非信心度）</small>}</div></div>
  {market?.components?.length?<><h3>盤面條件逐項對照</h3><p className="fine">價格距MA為正表示在均線上方、負表示下方；除以ATR是用當時波幅衡量距離。區間位置0接近近期低點、1接近高點；距支撐／壓力的ATR倍數越小，代表越靠近候選價位。均線斜率描述均線變化，不是交易員畫的趨勢線。</p><div className="table-scroll"><table><thead><tr><th>條件</th><th>本次</th><th>歷史案例</th><th>狀態</th></tr></thead><tbody>{market.components.map(c=><tr key={c.feature}><td>{c.label}</td><td>{comparisonValue(c.query)}</td><td>{comparisonValue(c.case)}</td><td>{c.missing?'資料不足':c.distance<=.25?'接近':'有差異'}</td></tr>)}</tbody></table></div></>:null}
 </section>;
}
