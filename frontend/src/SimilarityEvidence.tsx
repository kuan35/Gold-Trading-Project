import {comparisonValue,poolDescription} from './similarityPresentation';
import type {Case,Retrieval} from './types';
import {ContextPoolEvidence,ContextCaseEvidence} from './ContextEvidence';

const indicatorNames:Record<string,string>={
 '5m_ma_gap':'5 分｜價格距 MA20（ATR 倍）','5m_atr_pct':'5 分｜ATR 波動比例',
 '5m_rsi14':'5 分｜RSI14','5m_macd_hist':'5 分｜MACD 柱（ATR 倍）',
 '5m_slope':'5 分｜均線斜率（ATR 倍）','range_position':'5 分｜近 60 根區間位置',
 '15m_ma_gap':'15 分｜價格距 MA20（ATR 倍）','15m_atr_pct':'15 分｜ATR 波動比例',
 '15m_rsi14':'15 分｜RSI14','15m_macd_hist':'15 分｜MACD 柱（ATR 倍）',
 '1h_ma_gap':'1 小時｜價格距 MA20（ATR 倍）','1h_atr_pct':'1 小時｜ATR 波動比例',
};

export function PoolEvidence({pool}:{pool:Retrieval}){
 const text=poolDescription(pool),c=pool.comparison;
 if(c?.method==='context_contract_v1')return <ContextPoolEvidence pool={pool}/>;
 if(c?.method==='dual_path_structure_v1')return <section className="similarity-evidence" aria-label="雙週期路徑比較範圍">
  <strong>歷史案例 · 雙週期完整路徑＋前高低狀態</strong><p>{text.operation}</p><p>{text.market}；{text.reason}</p>
  <details><summary>如何檢索與行情來源</summary><p>五分60根看進場細節，一小時20根看背景。各窗首根收盤歸零，逐根計算百分比路徑差；前高低狀態相同者優先，再看兩軸中較差的相對排名、排名和。每個操作群及盤面時點只留一筆。</p><p>前高低取末五分棒之前20棒的最高／最低；波動倍率另列，不參與排名。來源是cTrader DEMO已收K線，沒有混入未收棒；歷史盤面時鐘尚未獨立核實，前五並非已通過足夠相似門檻。</p></details>
 </section>;
 if(c?.mode==='candidate_market')return <section className="similarity-evidence" aria-label="參考盤面比較範圍">
  <strong>歷史案例 · 參考盤面比對</strong>
  <div className="similarity-axes"><div><span className="fine">篩選條件</span><p>{text.operation}</p></div>
  <div><span className="fine">K 線路徑＋技術指標＋固定型態</span><p>{text.market}</p><p>{text.reason}</p></div></div>
  {c.query_pattern_code&&<p className="fine">本次三段走勢：<strong>{c.query_pattern_code}</strong>（U 上行／D 下行／S 盤整）</p>}
  {c.query_market_text&&<details><summary>本次盤面固定描述</summary><p>{c.query_market_text}</p></details>}
  <details><summary>如何檢索與行情來源</summary><p>只用相同買賣方向、查詢前已平倉且具可用參考盤面的案例。60 根已收五分鐘 K 線收盤路徑與指標各自計算距離，再在同一資料層轉成相對排名；先看兩軸中較差的排名。前 {c.rerank_window??15} 個不同操作群內，三段走勢型態相同的案例提前，其餘維持數值順序；最後展示前五。完整三週期與五分鐘限定分開，不跨層比較分數。</p><p>文字型態取自同一批 K 線，不是獨立證據。{c.basis==='synthetic_query_real_history'?'本頁用合成回放 K 線作查詢，對照公開的真實交易員案例；這只展示檢索流程，不能當成真實下單前的相似度驗證。':('query_source' in pool&&pool.query_source==='ctrader_demo_xauusd'?'本機即時查詢使用 cTrader DEMO 已收 K 線；當下 tick 只作時鐘，不混入未收盤 K 線。':'本機版使用回放時點的已收行情。')}參考行情依來源時間模型定位，券商原始時鐘尚未獨立核實。尚未完成盲評，沒有足夠相似門檻；排名不是準確率、獲利機率或交易建議。</p></details>
 </section>;
 return <section className="similarity-evidence" aria-label="相似案例比較範圍">
  <div className="similarity-axes"><div><span className="fine">操作條件</span><strong>{c?.basis==='direction_only'?'只比較方向':c?.basis==='relative_lot'?'比較相對平常手數':'比較絕對手數'}</strong><p>{text.operation}</p></div>
  <div><span className="fine">盤面條件</span><strong>{text.market}</strong><p>{text.reason}</p></div></div>
  {c?.basis!=='direction_only'&&c?.verified_market_candidates!==undefined&&<p className="fine">同方向／操作類型中，有 {c.verified_market_candidates} 個已成熟案例具可用盤面資料；{c.excluded_unverified_market??0} 個尚無可用盤面資料。候選群不是獨立交易。</p>}
  <details><summary>如何判斷相似</summary>{c?.basis==='direction_only'?<p>合成案例備援模式只依相同買賣方向與已成熟時間列出，沒有歷史盤面相似度。真實案例封包載入失敗時請查看頁面錯誤。</p>:<><p>先篩方向、首筆／加倉與已成熟案例。操作距離上限0.65；有可用時間證據及完整盤面資料時，再比較5分／15分／1小時趨勢、相對位置與波動，盤面距離上限0.40。兩個門檻必須各自通過，再按操作40%、盤面60%排序。</p><p>權重與門檻尚待評測；不是準確率或預測勝率。</p></>}</details>
 </section>;
}

export function CaseEvidence({item}:{item:Case}){
 const op=item.operation_comparison,market=item.market_comparison;
 if(item.retrieval_method==='context_contract_v1')return <ContextCaseEvidence item={item}/>;
 if(item.retrieval_method==='dual_path_structure_v1')return <section className="similarity-evidence" aria-label="雙週期案例差異">
  <strong>參考盤面 · 五分60根＋一小時20根</strong>
  <p>前高低狀態：{item.structure_label??'資料不足'}；{item.structure_match?'與查詢相同':'與查詢不同，屬補充參考'}。</p>
  <div className="similarity-axes"><div><span className="fine">五分鐘路徑</span><p>差距 {item.path_distance_pct?.toFixed(3)??'—'} 百分點；池內排名 {item.path_rank==null?'—':`${(item.path_rank*100).toFixed(1)}%`}。</p></div>
  <div><span className="fine">一小時路徑</span><p>差距 {item.hour_path_distance_pct?.toFixed(3)??'—'} 百分點；池內排名 {item.hour_path_rank==null?'—':`${(item.hour_path_rank*100).toFixed(1)}%`}。</p></div></div>
  <p>ATR波動倍率差 {item.volatility_ratio?.toFixed(2)??'—'} 倍（1為相同；另列不排名）。</p>
  <p className="fine">先看兩軸中較差的相對排名；以上數字是差距與先後，不是準確率或獲利機率。</p>
 </section>;
 if(item.candidate_tier)return <section className="similarity-evidence" aria-label="案例雙軸比對">
  <strong>參考盤面 · {item.candidate_tier==='full'?'完整三週期':'五分鐘限定'}</strong>
  <div className="similarity-axes"><div><span className="fine">K 線收盤路徑</span><p>同層相對排名 {item.path_rank==null?'資料不足':`${(item.path_rank*100).toFixed(1)}%`}；路徑差 {item.path_distance_pct==null?'資料不足':`${item.path_distance_pct.toFixed(3)} 個百分點`}。</p></div>
  <div><span className="fine">技術指標</span><p>同層相對排名 {item.indicator_rank==null?'資料不足':`${(item.indicator_rank*100).toFixed(1)}%`}；不是準確率。</p></div></div>
  {item.pattern_code&&<p className="fine">三段走勢 {item.pattern_code} · {item.pattern_match?'與本次型態相同':'與本次型態不同'}；型態僅在數值候選內重排。</p>}
  {item.market_state_text&&<details><summary>案例進場前固定描述</summary><p>{item.market_state_text}</p></details>}
  {item.indicator_differences&&<details><summary>指標差異</summary><p className="fine">下列數值是本次盤面與歷史案例的絕對差；同一欄越小越接近。不同指標的數字單位不同，請看上方同層相對排名。</p><div className="table-scroll"><table><tbody>{Object.entries(item.indicator_differences).map(([name,value])=><tr key={name}><th>{indicatorNames[name]||name}</th><td>{value.toFixed(4)}</td></tr>)}</tbody></table></div></details>}
  <details><summary>對時依據</summary><p>進場前盤面及進出場參考棒已按來源時間模型定位；券商原始時鐘尚未獨立核實。排名只比較下單前已知的 K 線與指標。{item.comparison_basis==='synthetic_query_real_history'?'本頁查詢 K 線為合成回放，不是真實即時行情。':''}</p></details>
 </section>;
 if(item.comparison_basis==='direction_only')return <section className="similarity-evidence" aria-label="合成案例比對範圍">
  <strong>合成示範 · 僅依買賣方向列出</strong>
  <p>手數、首筆或加倉及事後損益都不參與排序；此案例沒有歷史 K 線相似度。</p>
 </section>;
 return <section className="similarity-evidence" aria-label="案例分項比對">
  <div className="similarity-axes"><div><span className="fine">操作條件</span><strong>{op?.label||'操作條件比較'}{op?.strength==='weak'?' · 辨識力有限':''}</strong><p>{op?.reason||'比較方向、首筆／加倉與手數等條件。'}</p><small>操作距離 {op?.distance??item.operation_distance??item.distance??'未提供'}（越小越接近）</small></div>
  <div><span className="fine">盤面條件</span><strong>{market?.label||'盤面尚無法比較'}</strong><p>{market?.reason||'尚無已核實時間的盤面比較證據。'}</p>{market?.status==='matched'&&<small>盤面距離 {market.distance} · 可比較欄位權重覆蓋 {Math.round(market.coverage*100)}%（非信心度）</small>}</div></div>
  {market?.components?.length?<><h3>盤面條件逐項對照</h3><p className="fine">價格距MA為正表示在均線上方、負表示下方；除以ATR是用當時波幅衡量距離。區間位置0接近近期低點、1接近高點；距支撐／壓力的ATR倍數越小，代表越靠近候選價位。均線斜率描述均線變化，不是交易員畫的趨勢線。</p><div className="table-scroll"><table><thead><tr><th>條件</th><th>本次</th><th>歷史案例</th><th>狀態</th></tr></thead><tbody>{market.components.map(c=><tr key={c.feature}><td>{c.label}</td><td>{comparisonValue(c.query)}</td><td>{comparisonValue(c.case)}</td><td>{c.missing?'資料不足':c.distance<=.25?'接近':'有差異'}</td></tr>)}</tbody></table></div></>:null}
 </section>;
}
