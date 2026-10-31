import {useEffect,useMemo,useRef,useState} from 'react';import {api} from './api';import CaseComparisonCharts from './CaseComparisonCharts';import type {ComparisonSelection,ComparisonCharts} from './caseComparisonData';import AnalysisChart,{type AnalysisFrame,type Layer} from './AnalysisChart';import type {DraftInputState} from './conversationState';
type Charts=ComparisonCharts & {analysis?:{as_of_utc:string;frames:Record<'5m'|'15m'|'1h',AnalysisFrame>}};
export default function ConversationCharts({snapshotId,mode,light,onClose,initialPeriod='5m',reference,selection}:{snapshotId:string;mode:'analysis'|'cases';light:boolean;onClose:()=>void;initialPeriod?:'5m'|'15m'|'1h';reference?:DraftInputState;selection?:ComparisonSelection}){
 const [data,setData]=useState<Charts|null>(null),[error,setError]=useState(''),[period,setPeriod]=useState<'5m'|'15m'|'1h'>(initialPeriod),[annotations,setAnnotations]=useState(true),[focus,setFocus]=useState<string>();const host=useRef<HTMLElement>(null);
 useEffect(()=>{let active=true;setData(null);setError('');void api<Charts>(`/assistant/snapshots/${encodeURIComponent(snapshotId)}/charts`).then(v=>{if(v.snapshot_id!==snapshotId)throw Error('快照不一致。');if(active)setData(v);}).catch(e=>{if(active)setError(e instanceof Error?e.message:'圖表讀取失敗');});return()=>{active=false;};},[snapshotId]);
 const frame=data?.analysis?.frames[period];
 const shownFrame=useMemo(()=>{if(!frame)return null;const pending:Layer[]=[];
  for(const [field,label] of [['limit_price','準備中限價'],['sl','準備中停損'],['tp','準備中停利']] as const){const price=reference?.[field];if(field==='limit_price'&&reference?.order_type!=='LIMIT')continue;if(price?.trim()&&Number.isFinite(Number(price))&&Number(price)>0)pending.push({id:'draft.'+field,kind:'line',price,label:label+'（非分析結論）'});}
  return {...frame,layers:[...(annotations?frame.layers:[]),...pending]};
 },[frame,annotations,reference]);
 useEffect(()=>{if(data)host.current?.scrollIntoView({block:'start'});},[data]);
 return <section ref={host} className="cw-charts" aria-label="同頁固定快照圖表"><header><h2>{mode==='cases'?'進場前盤面對照':'分析快照 · 圖上依據'}</h2><button type="button" onClick={onClose}>收合圖表</button></header>
  {error&&<p role="alert">{error} 請重新提問取得新快照。</p>}{!data&&!error&&<p role="status">讀取原分析快照…</p>}
  {data&&<><p className="fine">{data.analysis?.as_of_utc??''} · 已收 K 棒固定快照，與持續更新的頁首 tick 分開。</p>
   {mode==='analysis'?<><div className="cw-actions">{(['5m','15m','1h'] as const).map(p=><button type="button" key={p} aria-pressed={period===p} onClick={()=>{setPeriod(p);setFocus(undefined);}}>{p==='1h'?'一小時':p==='5m'?'五分鐘':'十五分鐘'}</button>)}<label><input type="checkbox" checked={annotations} onChange={e=>setAnnotations(e.target.checked)}/>顯示程式註記</label></div>{shownFrame?.bars.length?<><AnalysisChart scope={snapshotId+':analysis:'+period} key={snapshotId+period+annotations} frame={shownFrame} light={light} ariaLabel={'分析快照 '+period} focus={focus}/><div className="cw-layer-list" aria-label="選擇圖上依據">{shownFrame.layers.map(l=><button key={l.id} type="button" aria-pressed={focus===l.id} onClick={()=>setFocus(focus===l.id?undefined:l.id)}>{l.label}</button>)}</div><details className="cw-chart-help"><summary>圖表說明</summary><p className="fine">MA20（金）／MA60（藍）。固定區間與轉折支撐壓力是不同依據；紫色虛線來自目前準備中欄位，與原分析快照分開，不代表成交或分析建議。點依據可加亮參考線。</p></details></>:<p>此週期已收棒不足，未使用即時資料替代。</p>}</>
   :<CaseComparisonCharts key={data.snapshot_id} data={data} light={light} initialCaseRef={selection?.caseRef} initialMinutes={selection?.minutes}/>}
  </>}
 </section>;
}
