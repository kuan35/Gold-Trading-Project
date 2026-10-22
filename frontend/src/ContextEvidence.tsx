import {poolDescription} from './similarityPresentation';
import type {Case,Retrieval} from './types';

export function ContextPoolEvidence({pool}:{pool:Retrieval}){
 const c=pool.comparison,text=poolDescription(pool),limits=c?.thresholds;
 return <section className="similarity-evidence" aria-label="情境相似規則檢查">
  <strong>{text.market}</strong><p>{text.reason}</p>
  {c?.query_event_label&&<p>目前階段：{c.query_event_label}；最近半小時：{c.query_tail_direction??'資料不足'}。</p>}
  <p>{text.operation}</p>
  {limits&&<p className="fine">路徑差距容忍：五分鐘 {limits.d5.toFixed(2)}、一小時 {limits.d1h.toFixed(2)}、最近半小時 {limits.dtail.toFixed(2)} 百分點；波動倍率最多 {limits.vol_ratio} 倍。事件階段必須相同，末段方向不能明顯相反。</p>}
  {pool.rule_status!=='INSUFFICIENT_DATA'&&<p>可比較 {c?.eligible_rows??0} 筆；通過條件 {c?.passed_rows??0} 筆；去重後 {pool.total} 群，最多展示五筆。</p>}
  {!!Object.keys(c?.rejections??{}).length&&<details><summary>查看未通過原因</summary>
   <ul>{Object.entries(c!.rejections!).map(([key,count])=><li key={key}>{c?.rejection_labels?.[key]??key}：{count} 筆</li>)}</ul>
   <p className="fine">同一案例可能同時違反多項，以上計數不可相加當作案例數。</p>
  </details>}
  {c?.query_market_text&&<details><summary>本次已收盤面描述</summary><p>{c.query_market_text}</p></details>}
  <details><summary>如何判斷與行情來源</summary>
   <p>五分鐘60根看短期走勢，一小時20根看背景；各窗從第一根收盤換成百分比路徑，另比較最近六根五分鐘棒。先用最近六根之前20棒固定區間，再判斷收盤越界或收回；影線越界不等於收盤突破。</p>
   <p>各項都通過試驗容忍才保留；先看差距占各項容忍比例中最大的一項，再看合計。每個操作群與盤面時點只留一筆，沒有通過者就回空，不用其他近鄰補滿。</p>
   <p>{'query_source' in pool&&pool.query_source==='ctrader_demo_xauusd'?'查詢來自 cTrader DEMO 已收K線。':'查詢使用本機回放的已收行情。'}歷史參考盤面依來源時間模型定位，原始時鐘尚未獨立核實。容忍仍是試驗設定，通過規則不是人工相似準確率或預測勝率。</p>
  </details>
 </section>;
}

export function ContextCaseEvidence({item}:{item:Case}){
 const limits=item.context_check?.thresholds;
 const metrics=[['五分鐘完整路徑',item.path_distance_pct,limits?.d5,'百分點'],
  ['一小時完整路徑',item.hour_path_distance_pct,limits?.d1h,'百分點'],
  ['最近半小時路徑',item.tail_path_distance_pct,limits?.dtail,'百分點'],
  ['波動倍率',item.volatility_ratio,limits?.vol_ratio,'倍']] as const;
 return <section className="similarity-evidence" aria-label="情境案例逐項差距">
  <strong>各項通過情境規則 · 試驗設定</strong>
  <p>目前階段：查詢「{item.query_event_label??'資料不足'}」／案例「{item.event_label??'資料不足'}」。</p>
  <p>最近半小時方向：查詢{item.query_tail_direction??'資料不足'}／案例{item.tail_direction??'資料不足'}。</p>
  <div className="table-scroll"><table><thead><tr><th>比較項目</th><th>實際差距</th><th>容忍上限</th></tr></thead>
   <tbody>{metrics.map(([label,value,limit,unit])=><tr key={label}><th>{label}</th><td>{value?.toFixed(unit==='倍'?2:3)??'—'} {unit}</td><td>{limit?.toFixed(unit==='倍'?2:3)??'—'} {unit}</td></tr>)}</tbody>
  </table></div>
  <p className="fine">各項越小越接近，波動1倍表示相同。先比較差距最大的標準化項目；不是信心度或獲利機率。券商原始時鐘尚未獨立核實。</p>
 </section>;
}
