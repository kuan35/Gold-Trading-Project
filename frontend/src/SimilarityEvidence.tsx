import {comparisonValue,poolDescription} from './similarityPresentation';
import type {Case,Retrieval} from './types';

export function PoolEvidence({pool}:{pool:Retrieval}){
 const text=poolDescription(pool),c=pool.comparison;
 if(c?.mode==='candidate_market')return <section className="similarity-evidence" aria-label="候選盤面比較範圍">
  <strong>候選盤面 · 券商時鐘未核實</strong>
  <div className="similarity-axes"><div><span className="fine">篩選條件</span><p>{text.operation}</p></div>
  <div><span className="fine">K 線形狀＋技術指標</span><p>{text.market}</p><p>{text.reason}</p></div></div>
  <details><summary>如何判斷相似</summary><p>只用相同買賣方向、查詢前已成熟的候選案例。K 線形狀與指標各自計算距離，再在同一資料層轉成相對排名；按兩軸中較差的排名排序。完整三週期與五分鐘限定分開，不跨層比較分數。</p><p>尚未完成盲評，沒有足夠相似門檻。排名不是準確率、獲利機率或交易建議。</p></details>
 </section>;
 return <section className="similarity-evidence" aria-label="相似案例比較範圍">
  <div className="similarity-axes"><div><span className="fine">操作條件</span><strong>{c?.basis==='direction_only'?'只比較方向':c?.basis==='relative_lot'?'比較相對平常手數':'比較絕對手數'}</strong><p>{text.operation}</p></div>
  <div><span className="fine">盤面條件</span><strong>{text.market}</strong><p>{text.reason}</p></div></div>
  {c?.verified_market_candidates!==undefined&&<p className="fine">同方向／操作類型中，有 {c.verified_market_candidates} 個已成熟案例具可用盤面資料；{c.excluded_unverified_market??0} 個尚無可用盤面資料。候選群不是獨立交易。</p>}
  <details><summary>如何判斷相似</summary>{c?.basis==='direction_only'?<p>公開版只用合成案例展示流程，依相同買賣方向與已成熟時間列出。沒有歷史盤面、手數或勝率模型。</p>:<><p>先篩方向、首筆／加倉與已成熟案例。操作距離上限0.65；有可用時間證據及完整盤面資料時，再比較5分／15分／1小時趨勢、相對位置與波動，盤面距離上限0.40。兩個門檻必須各自通過，再按操作40%、盤面60%排序。</p><p>權重與門檻尚待評測；不是準確率或預測勝率。</p></>}</details>
 </section>;
}

export function CaseEvidence({item}:{item:Case}){
 const op=item.operation_comparison,market=item.market_comparison;
 if(item.candidate_tier)return <section className="similarity-evidence" aria-label="候選案例雙軸比對">
  <strong>候選盤面 · 時鐘未核實 · {item.candidate_tier==='full'?'完整三週期':'五分鐘限定'}</strong>
  <div className="similarity-axes"><div><span className="fine">K 線形狀</span><p>同層相對排名 {item.shape_rank==null?'資料不足':`${(item.shape_rank*100).toFixed(1)}%`}；越低表示在本次候選池中越靠近。</p></div>
  <div><span className="fine">技術指標</span><p>同層相對排名 {item.indicator_rank==null?'資料不足':`${(item.indicator_rank*100).toFixed(1)}%`}；不是準確率。</p></div></div>
  {item.indicator_differences&&<details><summary>指標差異</summary><div className="table-scroll"><table><tbody>{Object.entries(item.indicator_differences).map(([name,value])=><tr key={name}><th>{name}</th><td>{value.toFixed(4)}</td></tr>)}</tbody></table></div></details>}
 </section>;
 return <section className="similarity-evidence" aria-label="案例分項比對">
  <div className="similarity-axes"><div><span className="fine">操作條件</span><strong>{op?.label||'操作條件比較'}{op?.strength==='weak'?' · 辨識力有限':''}</strong><p>{op?.reason||'比較方向、首筆／加倉與手數等條件。'}</p><small>操作距離 {op?.distance??item.operation_distance??item.distance??'未提供'}（越小越接近）</small></div>
  <div><span className="fine">盤面條件</span><strong>{market?.label||'盤面尚無法比較'}</strong><p>{market?.reason||'尚無已核實時間的盤面比較證據。'}</p>{market?.status==='matched'&&<small>盤面距離 {market.distance} · 可比較欄位權重覆蓋 {Math.round(market.coverage*100)}%（非信心度）</small>}</div></div>
  {market?.components?.length?<><h3>盤面條件逐項對照</h3><p className="fine">價格距MA為正表示在均線上方、負表示下方；除以ATR是用當時波幅衡量距離。區間位置0接近近期低點、1接近高點；距支撐／壓力的ATR倍數越小，代表越靠近候選價位。均線斜率描述均線變化，不是交易員畫的趨勢線。</p><div className="table-scroll"><table><thead><tr><th>條件</th><th>本次</th><th>歷史案例</th><th>狀態</th></tr></thead><tbody>{market.components.map(c=><tr key={c.feature}><td>{c.label}</td><td>{comparisonValue(c.query)}</td><td>{comparisonValue(c.case)}</td><td>{c.missing?'資料不足':c.distance<=.25?'接近':'有差異'}</td></tr>)}</tbody></table></div></>:null}
 </section>;
}
