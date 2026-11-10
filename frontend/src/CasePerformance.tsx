export type CasePerformanceData={status:string;total:number;known_results:number;wins:number;losses:number;flat:number;unknown_results:number;
 win_rate_pct:string|null;price_results_count:number;mean_price_return_pct:string|null;mean_move_per_oz:string|null;
 unknown_currency_results:number;pnl_by_currency:{currency:string;count:number;mean_pnl:string;mean_win:string|null;mean_loss:string|null}[]};
const pct=(value:string|null)=>value==null?'資料不足':value+'%';
export default function CasePerformance({data:d}:{data:CasePerformanceData}){
 return <section className="ag-case-preview" aria-label="歷史相似案例整體表現"><strong>歷史案例整體表現</strong>
  <p>全部 {d.total} 組相似案例 · 每組取一筆代表原單</p>
  <dl className="cw-operation-values">
   <div><dt>歷史獲利比例</dt><dd>{pct(d.win_rate_pct)} <small>（{d.wins}／{d.known_results}筆）</small></dd></div>
   <div><dt>平均價格報酬</dt><dd>{pct(d.mean_price_return_pct)} <small>（未扣成本）</small></dd></div>
   <div><dt>平均每盎司價差</dt><dd>{d.mean_move_per_oz??'資料不足'} USD/oz</dd></div>
   {d.pnl_by_currency.map(row=><div key={row.currency}><dt>平均單筆損益</dt><dd>{row.mean_pnl} {row.currency} <small>（{row.count}筆）</small></dd></div>)}
  </dl>
  {d.unknown_currency_results>0&&<p className="fine">另有 {d.unknown_currency_results} 筆幣別未載，未合併平均金額。</p>}
  {(d.unknown_results>0||d.price_results_count!==d.total)&&<p className="fine">報表損益有效 {d.known_results}／{d.total} 筆；進出價有效 {d.price_results_count}／{d.total} 筆。</p>}
  <details><summary>查看賺賠分布與平均賺賠</summary><p>獲利 {d.wins} 筆 · 虧損 {d.losses} 筆 · 損益為零 {d.flat} 筆 · 未知 {d.unknown_results} 筆</p>
   {d.pnl_by_currency.map(row=><p key={row.currency}>{row.currency}：獲利單平均 {row.mean_win??'無資料'}；虧損單平均 {row.mean_loss??'無資料'}</p>)}
   <p className="fine">完整匹配池的原單歷史結果；價格報酬採方向調整後的算術平均，金額含原手數差異。這些比例不是這次交易的獲利機率。</p>
  </details>
 </section>;
}
