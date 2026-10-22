import {useState} from 'react';
import {api} from './api';
import Chart from './Chart';
import type {Bar} from './types';
import CaseOperations from './CaseOperations';

export type CaseComparisonData={status:string;label:string;reason:string;method:string;side:string;snapshot_id:string|null;query_as_of_utc:number|null;
 query_state:{event:string;tail_direction:string};counts:{eligible:number|null;passed:number|null;displayed:number};
 cases:{ref:string;case_id?:string;event:string;tail_direction:string;similarities:string[];differences:string[];representative?:{result:string;profit:string|null;currency:string|null;currency_stated:boolean;side:string;action:string;lot:string|null};metrics:{key:string;label:string;actual:string|null;tolerance:string|null;unit:string;passed:boolean|null}[]}[];
 distribution?:{total:number|null;wins:number|null;losses:number|null;flat:number|null;unknown:number|null;basis:string};
 rejections:{key:string;label:string;count:number}[]};
type Candle=Omit<Bar,'volume'>;
type Charts={snapshot_id:string;query_as_of_utc:number|null;query:Record<'5m'|'1h',Candle[]>;cases:({ref:string;as_of_utc:number|null;clock_status:string}&Record<'5m'|'1h',Candle[]>)[]};
const utc=(time:number|null)=>time===null?'資料不足':new Date(time*1000).toISOString().replace('T',' ').replace('.000Z',' UTC');

export default function CaseComparison({comparison:c,snapshotId,hideCharts=false}:{comparison:CaseComparisonData;snapshotId:string|null;hideCharts?:boolean}){
 const [charts,setCharts]=useState<Charts|null>(null),[selected,setSelected]=useState(0),[opened,setOpened]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const load=async()=>{if(busy)return;if(charts){setOpened(v=>!v);return;}if(!snapshotId)return;
  setBusy(true);setError('');try{const next=await api<Charts>(`/assistant/snapshots/${encodeURIComponent(snapshotId)}/charts`);if(next.snapshot_id!==snapshotId)throw Error('快照不一致，未顯示對照圖。');setCharts(next);setOpened(true);}catch(e){setError(e instanceof Error?e.message:'無法讀取快照圖表');}finally{setBusy(false);}};
 const candidate=charts?.cases[selected];
 return <section className="case-comparison" aria-label="同一快照歷史案例比較">
  <header><strong>{c.label}</strong><span>{c.side} · 情境規則</span></header><p>{c.reason}</p>
  <p className="fine">合格觀察列 {c.counts.eligible??'未知'} · 通過操作群 {c.counts.passed??'未知'} · 展示 {c.counts.displayed} 組。已收棒截止：{utc(c.query_as_of_utc)}</p>
  {!!c.rejections.length&&<><ul>{c.rejections.map(r=><li key={r.key}>{r.label}：{r.count} 列</li>)}</ul><p className="fine">一列可有多個未通過原因，不能相加當作案例總數。</p></>}
  {c.cases.map(item=><details key={item.ref}><summary>{item.ref} · {item.event} · 末段{item.tail_direction}</summary><p className="fine">{item.similarities.join('；')}</p>
   <table><caption className="sr-only">{item.ref}逐項比較</caption><thead><tr><th>比較項目</th><th>實際差距</th><th>試驗容忍</th><th>結果</th></tr></thead><tbody>{item.metrics.map(m=><tr key={m.key}><th scope="row">{m.label}</th><td>{m.actual===null?'資料不足':m.actual+m.unit}</td><td>{m.tolerance===null?'資料不足':m.tolerance+m.unit}</td><td>{m.passed===null?'資料不足':m.passed?'符合':'需核對'}</td></tr>)}</tbody></table><CaseOperations snapshotId={snapshotId} caseRef={item.ref}/></details>)}
  {!hideCharts&&!!c.cases.length&&snapshotId&&<button type="button" disabled={busy} onClick={()=>void load()}>{busy?'讀取固定快照…':opened?'收合 K 線':'對照同一快照 K 線'}</button>}
  {error&&<p role="alert" className="modal-error">{error}</p>}
  {opened&&charts&&<section className="case-chart-comparison" aria-label="固定快照五分鐘與一小時對照"><h3>進場前盤面對照</h3>
   <label>選擇案例<select value={selected} onChange={e=>setSelected(Number(e.target.value))}>{charts.cases.map((row,i)=><option key={row.ref} value={i}>{row.ref}</option>)}</select></label>
   <p className="fine">固定快照 {snapshotId?.slice(0,8)} · 查詢 {utc(charts.query_as_of_utc)} · 歷史參考 {utc(candidate?.as_of_utc??null)}。原始時鐘未知；兩邊只顯示各自決策前已收棒，價位尺度各自顯示。</p>
   <div className="case-chart-grid">{(['5m','1h'] as const).flatMap(interval=>[<section key={interval+'query'}><h4>查詢盤面 · {interval==='5m'?'五分鐘':'一小時'}</h4>{charts.query[interval].length?<Chart bars={charts.query[interval]} light={false} averages={false} showVolume={false} ariaLabel={'查詢盤面'+interval}/>:<p>此快照的已收棒不足。</p>}</section>,<section key={interval+'case'}><h4>{candidate?.ref} · {interval==='5m'?'五分鐘':'一小時'}</h4>{candidate?.[interval]?.length?<Chart bars={candidate[interval]} light={false} averages={false} showVolume={false} ariaLabel={'歷史參考'+interval}/>:<p>此案例缺少可顯示的參考 K 線。</p>}</section>])}</div>
  </section>}
  <p className="fine">只比較進場前盤面；手數與盈虧不排名。通過自定條件不等於完全相同，原始案例時鐘尚未獨立核實。</p>
 </section>;
}
