import {useState} from 'react';
import ConversationCharts from './ConversationCharts';
import CaseOperations from './CaseOperations';

export type CaseComparisonData={status:string;label:string;reason:string;method:string;side:string;snapshot_id:string|null;query_as_of_utc:number|null;
 tick_volume?:{enabled:boolean;limit?:string;query_relative?:string|null;query_status?:string;query_reason?:string|null};
 query_state:{event:string;tail_direction:string};counts:{eligible:number|null;passed:number|null;displayed:number};
 cases:{ref:string;case_id?:string;event:string;tail_direction:string;similarities:string[];differences:string[];tick_activity?:{query_relative:string;case_relative:string;multiplier:string;limit:string}|null;representative?:{result:string;profit:string|null;currency:string|null;currency_stated:boolean;side:string;action:string;lot:string|null};metrics:{key:string;label:string;actual:string|null;tolerance:string|null;unit:string;passed:boolean|null}[]}[];
 distribution?:{total:number|null;wins:number|null;losses:number|null;flat:number|null;unknown:number|null;basis:string};
 rejections:{key:string;label:string;count:number}[]};
const utc=(time:number|null)=>time===null?'資料不足':new Date(time*1000).toISOString().replace('T',' ').replace('.000Z',' UTC');

export default function CaseComparison({comparison:c,snapshotId,hideCharts=false}:{comparison:CaseComparisonData;snapshotId:string|null;hideCharts?:boolean}){
 const [opened,setOpened]=useState(false);
 return <section className="case-comparison" aria-label="同一快照歷史案例比較">
  <header><strong>{c.label}</strong><span>{c.side} · 情境規則</span></header><p>{c.reason}</p>
  {c.tick_volume?.enabled&&<p>已納入 tick 報價活躍度，非成交量。量比為末根已收五分K與前20根均量比較；目前量比 {c.tick_volume.query_relative??'無法比較'}，與歷史案例差距最多 {c.tick_volume.limit??'未知'} 倍。</p>}
  <p className="fine">合格觀察列 {c.counts.eligible??'未知'} · 通過操作群 {c.counts.passed??'未知'} · 展示 {c.counts.displayed} 組。已收棒截止：{utc(c.query_as_of_utc)}</p>
  {!!c.rejections.length&&<><ul>{c.rejections.map(r=><li key={r.key}>{r.label}：{r.count} 列</li>)}</ul><p className="fine">一列可有多個未通過原因，不能相加當作案例總數。</p></>}
  {c.cases.map(item=><details key={item.ref}><summary>{item.ref} · {item.event} · 末段{item.tail_direction}</summary><p className="fine">{item.similarities.join('；')}</p>
   {item.tick_activity&&<p>目前量比 {item.tick_activity.query_relative} · 歷史量比 {item.tick_activity.case_relative} · 活躍度差距 {item.tick_activity.multiplier} 倍</p>}
   <table><caption className="sr-only">{item.ref}逐項比較</caption><thead><tr><th>比較項目</th><th>實際差距</th><th>試驗容忍</th><th>結果</th></tr></thead><tbody>{item.metrics.map(m=><tr key={m.key}><th scope="row">{m.label}</th><td>{m.actual===null?'資料不足':m.actual+m.unit}</td><td>{m.tolerance===null?'資料不足':m.tolerance+m.unit}</td><td>{m.passed===null?'資料不足':m.passed?'符合':'需核對'}</td></tr>)}</tbody></table><CaseOperations snapshotId={snapshotId} caseRef={item.ref}/></details>)}
  {!hideCharts&&!!c.cases.length&&snapshotId&&<button type="button" onClick={()=>setOpened(v=>!v)}>{opened?'收合 K 線':'對照同一快照 K 線'}</button>}
  {opened&&snapshotId&&<ConversationCharts snapshotId={snapshotId} mode="cases" light={false} onClose={()=>setOpened(false)}/>}
  <p className="fine">只比較進場前盤面；手數與盈虧不排名。通過自定條件不等於完全相同，原始案例時鐘尚未獨立核實。</p>
 </section>;
}
