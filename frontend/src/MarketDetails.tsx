import type {Technical} from './types';

export default function MarketDetails({analysis:a}:{analysis?:Technical}) {
  if(!a)return null;
  const value=(v:string|null)=>v??'根數不足';
  return <details className="market-details">
    <summary>盤面數據 · {a.interval} 已收K棒 <span>快照 {a.last_closed_at?new Date(a.last_closed_at*1000).toISOString().replace('T',' ').slice(0,16)+' UTC':'資料不足'}</span></summary>
    {a.reading&&<section className="market-reading" aria-label="盤面方向與判斷依據"><header><span>此週期盤面解讀</span><strong>{a.reading.label}</strong></header><p>{a.reading.reasons[0]}</p><p className="fine">{a.reading.reasons.slice(1).join(' ')}</p></section>}
    <div className="indicator-grid">
      <div><span>動能 RSI 14</span><strong>{value(a.rsi14)}</strong><small>{a.reading?.indicators.rsi||'0–100；比較近期漲跌動能'}</small></div>
      <div><span>MACD 12 / 26 / 9</span><strong>{value(a.macd_line)}</strong><small>訊號 {value(a.macd_signal)} · 柱 {value(a.macd_histogram)}</small><small>{a.reading?.indicators.macd}</small></div>
      <div><span>波動 ATR 14</span><strong>{value(a.atr14)} <small>USD / oz</small></strong><small>{a.reading?.indicators.atr||'近期真實波幅的平滑平均；不分多空'}</small></div>
      <div><span>布林通道 20 / 2</span><strong>{value(a.boll_middle)}</strong><small>下 {value(a.boll_lower)} · 上 {value(a.boll_upper)}</small><small>{a.reading?.indicators.bollinger}</small></div>
      <div><span>來源量比</span><strong>{a.source_volume_ratio?`${a.source_volume_ratio} 倍`:'資料不足'}</strong><small>{a.reading?.indicators.volume||'末根／前20根平均；非全球量'}</small></div>
    </div>
    <div className="level-grid">{([['support','候選支撐'],['resistance','候選壓力']] as const).map(([kind,label])=><div key={kind}><strong>{label}</strong>{a.levels[kind].length?a.levels[kind].map(v=><p key={v.price}><b>{v.price}</b><span>{v.pivot_count} 個轉折歸併 · 確認於 {new Date(v.confirmed_at*1000).toISOString().replace('T',' ').slice(5,16)} UTC</span></p>):<p>目前沒有符合條件的候選價位</p>}</div>)}</div>
    <p className="fine">支撐是價格下方的候選參考區，壓力是上方的候選參考區；不是必守價位或交易員畫線。以上描述當前結構，不預測下一根。定位舊成交時，這裡仍是目前回放快照的分析。</p>
    <details><summary>計算與判讀方法</summary><p className="fine">{a.reading?.method}</p><p className="fine">{a.definitions}</p><p className="fine">{a.levels.method} 計算窗口為最近 {a.levels.lookback_count} 根。</p></details>
  </details>;
}
