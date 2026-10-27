import {useEffect,useMemo,useState} from 'react';import {api} from './api';import Chart from './Chart';import OutcomeSummary from './OutcomeSummary';
import {historicalDisplay,matchingOutcome,type ComparisonCharts,type ExpandedOutcome,type HorizonMinutes} from './caseComparisonData';
const utc=(t?:number|null)=>typeof t==='number'?new Date(t*1000).toISOString().replace('T',' ').replace('.000Z',' UTC'):'資料不足';
export default function CaseComparisonCharts({data,light,initialCaseRef,initialMinutes=60}:{data:ComparisonCharts;light:boolean;initialCaseRef?:string;initialMinutes?:HorizonMinutes}){
 const [caseRef,setCaseRef]=useState(()=>data.cases.find(c=>c.ref===initialCaseRef)?.ref??data.cases[0]?.ref??''),[minutes,setMinutes]=useState<HorizonMinutes>(initialMinutes);
 const [result,setResult]=useState<{key:string;value:ExpandedOutcome}|null>(null),[error,setError]=useState<{key:string;text:string}|null>(null);
 const candidate=data.cases.find(c=>c.ref===caseRef),requestKey=JSON.stringify([data.snapshot_id,caseRef,minutes]);
 const outcome=result?.key===requestKey?result.value:null,shownError=error?.key===requestKey?error.text:'';
 useEffect(()=>{let active=true;if(!caseRef)return;
  void api<ExpandedOutcome>(`/assistant/snapshots/${encodeURIComponent(data.snapshot_id)}/outcomes?case_ref=${encodeURIComponent(caseRef)}&minutes=${minutes}`).then(value=>{
   if(!matchingOutcome(value,data.snapshot_id,caseRef,minutes))throw Error('後續資料與原快照不一致，請重新提問。');
   if(active){setResult({key:requestKey,value});setError(null);}
  }).catch(e=>{if(active)setError({key:requestKey,text:e instanceof Error?e.message:'後續資料無法讀取'});});
  return()=>{active=false;};
 },[data.snapshot_id,caseRef,minutes,requestKey]);
 const historical=useMemo(()=>historicalDisplay(candidate?.['5m']??[],outcome?.history),[candidate,outcome]);
 return <div className="case-fused-comparison" aria-label="同案例進場前與歷史後續對照">
  <div className="scenario-controls"><label>歷史案例<select value={caseRef} onChange={e=>setCaseRef(e.target.value)} disabled={!data.cases.length}>{data.cases.map(c=><option key={c.ref} value={c.ref}>{c.ref}</option>)}</select></label>
   <div role="group" aria-label="接在歷史五分K後的觀察期間">{([5,30,60] as const).map(n=><button key={n} type="button" aria-pressed={minutes===n} onClick={()=>setMinutes(n)}>後續 {n===60?'1 小時':n+' 分鐘'}</button>)}</div>
  </div>
  <p className="fine">查詢截止 {utc(data.query_as_of_utc)} · 歷史參考 {utc(candidate?.as_of_utc)}</p>
  <div className="cw-comparison-grid case-fused-grid">
   <section><h3>查詢 · 五分 60 棒</h3><p className="case-chart-caption">只顯示當時已收棒；右側留白供對照。</p>{data.query['5m'].length?<Chart bars={data.query['5m']} light={light} averages={false} showVolume={false} paddingBars={historical.futureCount+2} ariaLabel="查詢五分K，只顯示決策前已收棒"/>:<p>資料不足</p>}</section>
   <section><h3>{candidate?.ref??'未選取案例'} · 五分 60 棒＋歷史後續</h3><p className="case-chart-caption">金色圓點為後續起點 · 全部使用五分K</p>{historical.bars.length?<Chart bars={historical.bars} markers={historical.markers} light={light} averages={false} showVolume={false} paddingBars={2} ariaLabel={(candidate?.ref??'歷史')+'五分K，進場前與後續'+minutes+'分鐘'}/>:<p>沒有可顯示的歷史盤面。</p>}</section>
   <section className="case-fused-outcome" aria-label="圖上案例的後續數值"><h3>{candidate?.ref??'歷史案例'} · 後續 {minutes} 分鐘</h3>
    {!candidate?<p>沒有符合案例。</p>:shownError?<p role="alert">{shownError} 進場前圖仍可查看。</p>:!outcome?<p role="status">讀取同一快照的歷史後續…</p>:<><OutcomeSummary history={outcome.history} scenario={outcome.scenario} frozen/>{outcome.history.status==='AVAILABLE'&&!historical.futureCount&&<p role="alert">前後圖表時間未能安全銜接，保留進場前圖，沒有補棒。</p>}</>}
   </section>
   {(['query','case'] as const).map(which=><section key={which}><h3>{which==='query'?'查詢':candidate?.ref??'歷史案例'} · 一小時 20 棒</h3><p className="case-chart-caption">進場前背景</p>{(which==='query'?data.query['1h']:candidate?.['1h'])?.length?<Chart bars={which==='query'?data.query['1h']:candidate!['1h']} light={light} averages={false} showVolume={false} paddingBars={2} ariaLabel={(which==='query'?'查詢':'歷史案例')+'一小時進場前背景'}/>:<p>此快照資料不足。</p>}</section>)}
  </div>
  <details className="cw-chart-help"><summary>圖表與計算說明</summary><p className="fine">只以進場前盤面檢索；歷史後續不參與相似排名，也沒有繪製查詢盤面的未來。各圖保留原始價位與實際時間；後續從參考進場後首根完整五分棒開盤起算，未補棒或跨缺口計算。百分比依做多／做空方向調整。情境損失套用原分析草稿，未套退出、不含成本。歷史來源為 HistData BID 專題參考盤面，原始時鐘未獨立核實。</p></details>
 </div>;
}
