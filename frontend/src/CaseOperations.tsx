import TradeResult,{type PriceResult} from './TradeResult';
import {useEffect,useRef,useState} from 'react';import Decimal from 'decimal.js';import {api} from './api';
type OperationRow={price_result?:PriceResult;index:number|null;side:string|null;lot:string|null;entry:string|null;exit:string|null;profit:string|null;currency:string|null;result:string;role:string|null;ordering_uncertain:boolean};
export type OperationDetails={snapshot_id:string;case_ref:string;as_of_utc:string;status:string;provided_rows:number;displayed_rows:number;reported_total:number|null;coverage:string;truncated:boolean;limitations:string[];representative:{price_result?:PriceResult;side:string|null;action:string|null;lot:string|null;entry:string|null;exit:string|null;profit:string|null;currency:string|null};rows:OperationRow[]};
export const operationLabel=(value?:string|null)=>({FIRST:'可見初始單',ADD:'可見加倉',OPPOSITE:'可見反向操作'}[value??'']??'操作脈絡未提供');
const number=(value:string|null)=>{try{return value!==null&&new Decimal(value).isFinite()?value:'未提供';}catch{return '未提供';}};
const currency=(value:string|null)=>value&&/^[A-Z]{3}$/.test(value)?value:'幣別未載';
const side=(value:string|null)=>value==='BUY'?'做多':value==='SELL'?'做空':'方向未載';
export async function loadCaseOperations(snapshotId:string,caseRef:string,request:(path:string)=>Promise<unknown>=api):Promise<OperationDetails>{
 const raw=await request(`/assistant/snapshots/${encodeURIComponent(snapshotId)}/operations?case_ref=${encodeURIComponent(caseRef)}`);
 if(!raw||typeof raw!=='object')throw Error('操作明細格式無效。');
 const value=raw as OperationDetails;
 if(value.snapshot_id!==snapshotId)throw Error('操作明細快照不一致，未顯示其他時點資料。');
 if(value.case_ref!==caseRef)throw Error('操作明細案例不一致，未替換案例。');
 if(!Array.isArray(value.rows)||value.rows.length>100||!value.representative||!Array.isArray(value.limitations)||!value.rows.every(row=>row&&typeof row==='object'))throw Error('操作明細格式無效。');
 return value;
}
export function CaseOperationsView({data:d}:{data:OperationDetails}){
 return <section className="cw-operation-details" aria-label="原分析快照同群操作明細"><p className="fine">原分析 {new Date(d.as_of_utc).toLocaleString('zh-TW',{hour12:false})} · 歷史參考 · 原始券商時鐘未核實</p>
  <p><strong>{operationLabel(d.representative.action)}</strong> · {side(d.representative.side)} {number(d.representative.lot)} 手</p>
  <dl className="cw-operation-values"><div><dt>代表單筆進場</dt><dd>{number(d.representative.entry)}</dd></div><div><dt>代表單筆平倉</dt><dd>{number(d.representative.exit)}</dd></div><div><dt>代表單筆原報表結果</dt><dd>{number(d.representative.profit)} · {currency(d.representative.currency)}</dd></div></dl>
  <TradeResult result={d.representative.price_result}/><p>來源可見 {d.provided_rows} 筆，展示 {d.displayed_rows} 筆；來源記載 {d.reported_total??'未知'} 筆。</p>
  {d.coverage==='PARTIAL'&&<p className="cw-note">尚未顯示完整記載筆數；序列可能有缺漏或截斷。</p>}{d.coverage==='COUNT_CONFLICT'&&<p className="cw-note">來源記載筆數與可見序列不一致，請以逐列資料核對。</p>}
  {!d.rows.length&&<p>此快照沒有可見群內序列，沒有把代表單筆當作整組。</p>}
  <ol className="cw-operation-list">{d.rows.map((r,i)=><li key={i}><header><strong>來源序號 {r.index??'未載'} · {r.role??'操作未分類'}</strong><span>{side(r.side)} {number(r.lot)} 手</span></header>{r.ordering_uncertain&&<small>同時點順序未確認</small>}<dl className="cw-operation-values"><div><dt>進場價</dt><dd>{number(r.entry)}</dd></div><div><dt>平倉價</dt><dd>{number(r.exit)}</dd></div><div><dt>單筆原報表結果</dt><dd className={r.result==='LOSS'?'negative':r.result==='WIN'?'positive':''}>{number(r.profit)} · {currency(r.currency)}</dd></div></dl><TradeResult result={r.price_result}/></li>)}</ol>
  {!!d.limitations.length&&<details><summary>資料說明</summary>{d.limitations.map((text,i)=><p className="fine" key={i}>{text}</p>)}</details>}
 </section>;
}
export default function CaseOperations({snapshotId,caseRef}:{snapshotId:string|null;caseRef:string}){
 const [data,setData]=useState<OperationDetails|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState('');const request=useRef(0),loading=useRef(false);
 useEffect(()=>{request.current+=1;loading.current=false;setData(null);setBusy(false);setError('');return()=>{request.current+=1;};},[snapshotId,caseRef]);
 const load=async()=>{if(!snapshotId||loading.current||data)return;const sent=++request.current;loading.current=true;setBusy(true);setError('');
  try{const next=await loadCaseOperations(snapshotId,caseRef);if(sent===request.current)setData(next);}
  catch(e){if(sent===request.current)setError(e instanceof Error?e.message:'操作明細讀取失敗。');}
  finally{if(sent===request.current){loading.current=false;setBusy(false);}}
 };
 return <details className="cw-operations" onToggle={e=>{if(e.currentTarget.open)void load();}}><summary>同群可見操作</summary>
  {!snapshotId&&<p>沒有原分析快照，請重新提問以取得操作明細。</p>}{busy&&<p role="status">讀取原快照操作明細…</p>}{error&&<p role="alert">{error} <button type="button" onClick={()=>void load()}>重試讀取</button></p>}{data&&<CaseOperationsView data={data}/>}</details>;
}
