import CaseReviewPanel from './CaseReviewPanel';
import TradeResult,{TradeReturnSummary,executionReturnMarkers,priceReturnDisplay} from './TradeResult';
import {useEffect,useMemo,useState} from 'react';
import {api} from './api';import Chart from './Chart';import OutcomeSummary from './OutcomeSummary';
import {historicalDisplay,matchingOutcome,type ComparisonCharts,type ExpandedOutcome,type HorizonMinutes} from './caseComparisonData';
import {executionDisplay,executionFocusRange} from './caseExecutionDisplay';
import HoldingObservation from './HoldingObservation';
const utc=(t?:number|null)=>typeof t==='number'?new Date(t*1000).toISOString().replace('T',' ').replace('.000Z',' UTC'):'資料不足';
type Focus='ALL'|'ENTRY'|'CLOSE';

export default function CaseComparisonCharts({data,light,initialCaseRef,initialMinutes}:{data:ComparisonCharts;light:boolean;initialCaseRef?:string;initialMinutes?:HorizonMinutes}){
 const [caseRef,setCaseRef]=useState(()=>data.cases.find(c=>c.ref===initialCaseRef)?.ref??data.cases[0]?.ref??'');
 const [sync,setSync]=useState(true);
 const [minutes,setMinutes]=useState<HorizonMinutes>(initialMinutes??60),[actualClose,setActualClose]=useState(initialMinutes===undefined),[hover,setHover]=useState('');
 const [view,setView]=useState<{key:string;focus:Focus;revision:number}>({key:'',focus:'ALL',revision:0});
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
 const execution=candidate?.execution;
 const executionFrame=useMemo(()=>executionDisplay(candidate?.['5m']??[],execution),[candidate,execution]);
 const historical=useMemo(()=>historicalDisplay(candidate?.['5m']??[],outcome?.history),[candidate,outcome]);
 const showExecution=actualClose&&executionFrame.bars.length>0;
 const fullHolding=showExecution&&execution?.coverage?.scope==='WHOLE_REFERENCE_HOLDING';
 const fixedBars=useMemo(()=>{
  const entry=executionFrame.bars.length?execution?.bars[0]:null;
  if(!entry||!historical.bars.length||historical.bars.some(b=>b.time===entry.time)||entry.time<=historical.bars[0].time)return historical.bars;
  return [...historical.bars,entry].sort((a,b)=>a.time-b.time);
 },[executionFrame,execution,historical.bars]);
 const shownBars=showExecution?executionFrame.bars:fixedBars;
 const markers=useMemo(()=>{
  const availableTimes=new Set(shownBars.map(b=>b.time));
  const raw=showExecution?executionFrame.markers:execution?.markers??[];
  return [...(showExecution?[]:historical.markers),...executionReturnMarkers(raw,execution?.result).filter(m=>availableTimes.has(m.time))].sort((a,b)=>a.time-b.time);
 },[shownBars,showExecution,executionFrame,execution,historical.markers]);
 const entryRange=executionFocusRange(shownBars,markers,'ENTRY'),exitRange=executionFocusRange(shownBars,markers,'CLOSE');
 const viewKey=JSON.stringify([data.snapshot_id,caseRef,showExecution,minutes]);
 const focus=view.key===viewKey?view.focus:'ALL';
 const logicalRange=focus==='ENTRY'?entryRange:focus==='CLOSE'?exitRange:null;
 // Focus a real contiguous slice, not just its viewport: the chart's minimum zoom
 // must not reveal an unrelated segment when this slice contains only one bar.
 const plottedBars=useMemo(()=>logicalRange?shownBars.slice(logicalRange.from,logicalRange.to+1):shownBars,[shownBars,logicalRange?.from,logicalRange?.to]);
 const plottedMarkers=useMemo(()=>{const times=new Set(plottedBars.map(b=>b.time));return markers.filter(m=>times.has(m.time));},[plottedBars,markers]);
 const chooseFocus=(next:Focus)=>{setHover('');setView(previous=>({key:viewKey,focus:next,revision:previous.revision+1}));};
 const resetView=()=>setView(previous=>({key:'',focus:'ALL',revision:previous.revision+1}));
 const choosePeriod=(period:HorizonMinutes)=>{setMinutes(period);setActualClose(false);setHover('');resetView();};
 const executionHover=(time:number|null)=>setHover((execution?.markers??[]).filter(m=>m.time===time).map(m=>m.text).join('／'));
 const hoverLabel=hover&&execution?.result?.status==='AVAILABLE'?`${hover} · 原單 ${execution.result.entry_price} → ${execution.result.exit_price} · 價格報酬率（未扣交易成本） ${priceReturnDisplay(execution.result).text} · 價差 ${execution.result.move_per_oz} USD/oz`:undefined;
 useEffect(()=>{setHover('');},[caseRef,minutes,data.snapshot_id]);
 return <div className="case-fused-comparison" aria-label="同案例進場前與歷史後續對照">
  <div className="scenario-controls"><button type="button" aria-pressed={sync} onClick={()=>setSync(v=>!v)}>雙圖同步：{sync?'開':'關'}</button>
   <label>歷史案例<select aria-label="歷史案例" value={caseRef} onChange={e=>{setCaseRef(e.target.value);setHover('');resetView();}} disabled={!data.cases.length}>{data.cases.map(c=><option key={c.ref} value={c.ref}>{c.ref}</option>)}</select></label>
   <div role="group" aria-label="歷史圖顯示範圍">
    <button type="button" aria-pressed={showExecution} disabled={!executionFrame.bars.length} onClick={()=>{setActualClose(true);setHover('');resetView();}}>原單進出場</button>
    {([5,30,60] as const).map(n=><button key={n} type="button" aria-pressed={!showExecution&&minutes===n} onClick={()=>choosePeriod(n)}>後續 {n===60?'1 小時':n+' 分鐘'}</button>)}
   </div>
  </div>
  <CaseReviewPanel key={JSON.stringify([data.snapshot_id,caseRef])} snapshotId={data.snapshot_id} caseRef={caseRef||undefined}/>
  <p className="fine">查詢截止 {utc(data.query_as_of_utc)} · 歷史參考 {utc(candidate?.as_of_utc)}</p>
    <div className="case-chart-navigation" role="group" aria-label="歷史K線定位"><span>歷史圖定位</span>
     <button type="button" aria-pressed={focus==='ENTRY'} disabled={!entryRange} onClick={()=>chooseFocus('ENTRY')}>看進場</button>
     <button type="button" aria-pressed={focus==='CLOSE'} disabled={!exitRange} title={!exitRange?'目前範圍沒有可定位的出場棒；可切換原單進出場查看。':undefined} onClick={()=>chooseFocus('CLOSE')}>看出場</button>
     <button type="button" aria-pressed={focus==='ALL'} disabled={!shownBars.length} onClick={()=>chooseFocus('ALL')}>完整對照</button>
    </div>
    {showExecution&&executionFrame.gaps.length>0&&<details className="case-gap-note"><summary>{fullHolding?'來源時間間隔':'中間時段未展開'} · {executionFrame.gaps.length} 段時間間隔</summary><p>{fullHolding?'已載入持倉期間來源可用K棒；間隔可能含休市或來源缺漏，沒有插值。':'未補入中間K棒，間隔可能包含休市。'}橫向棒距不代表實際經過時間。</p><ul>{executionFrame.gaps.map(gap=><li key={gap.to}>{utc(gap.from)} → {utc(gap.to)}</li>)}</ul></details>}
  <div className="cw-comparison-grid case-fused-grid">
   <section>
    <h3>查詢 · 五分 60 棒</h3><p className="case-chart-caption">只顯示當時已收棒；右側留白供對照。</p>
    {data.query['5m'].length?<Chart syncGroup={sync?data.snapshot_id+caseRef+'5m':undefined} syncAnchor={data.query['5m'].length-1} scope={data.snapshot_id+':query:5m'} bars={data.query['5m']} light={light} averages={false} showVolume={false} paddingBars={Math.max(0,shownBars.length-data.query['5m'].length)+2} ariaLabel="查詢五分K，只顯示決策前已收棒"/>:<p>資料不足</p>}
   </section>
   <section>
    <h3>{candidate?.ref??'未選取案例'} · {showExecution?'原單進出場參考':'五分 60 棒＋歷史後續'}</h3>
    <p className="case-chart-caption">{showExecution?'綠色上箭頭為進場，紅色下箭頭為出場。':'金點為固定後續起點；進出箭頭僅在所選期間內顯示。'}{fullHolding&&`持倉已載入 ${execution?.coverage?.available_bars} 根五分K。`}</p>
    {plottedBars.length?<Chart syncGroup={sync?data.snapshot_id+caseRef+'5m':undefined} syncAnchor={plottedBars.findIndex(b=>b.time===candidate?.['5m'].at(-1)?.time)} scope={data.snapshot_id+':'+caseRef+':5m:'+viewKey} bars={plottedBars} annotation={<TradeReturnSummary result={execution?.result}/>} markers={plottedMarkers} hoverLabel={hoverLabel} onHoverTime={executionHover} light={light} averages={false} showVolume={false} paddingBars={2} logicalRange={logicalRange?{from:0,to:plottedBars.length+2}:null} resetToken={view.revision} ariaLabel={(candidate?.ref??'歷史')+(showExecution?'五分K，原單進場與出場':'五分K，進場前與後續'+minutes+'分鐘')}/>:<p>沒有可顯示的歷史盤面。</p>}
   </section>
   <section className="case-fused-outcome" aria-label="圖上案例的後續數值">
    <h3>{candidate?.ref??'歷史案例'} · 固定後續 {minutes} 分鐘</h3>
    {!!hover&&<p role="status">{hover} · 原單價格結果如下</p>}
    {execution?.result&&<details className="case-trade-details"><summary>原單價格與報酬明細</summary><TradeResult result={execution.result}/></details>}
    {candidate?.holding_observation&&<HoldingObservation observation={candidate.holding_observation}/>}
    {!executionFrame.bars.length&&<p>{executionFrame.reason}</p>}
    {!candidate?<p>沒有符合案例。</p>:shownError?<p role="alert">{shownError} 進場前圖仍可查看。</p>:!outcome?<p role="status">讀取同一快照的歷史後續…</p>:<><OutcomeSummary history={outcome.history} scenario={outcome.scenario} frozen/>{outcome.history.status==='AVAILABLE'&&!historical.futureCount&&<p role="alert">前後圖表時間未能安全銜接，保留進場前圖，沒有補棒。</p>}</>}
   </section>
   {(['query','case'] as const).map(which=><section key={which}><h3>{which==='query'?'查詢':candidate?.ref??'歷史案例'} · 一小時 20 棒</h3><p className="case-chart-caption">進場前背景</p>{(which==='query'?data.query['1h']:candidate?.['1h'])?.length?<Chart syncGroup={sync?data.snapshot_id+caseRef+'1h':undefined} scope={data.snapshot_id+':'+which+':'+caseRef+':1h'} bars={which==='query'?data.query['1h']:candidate!['1h']} light={light} averages={false} showVolume={false} paddingBars={2} ariaLabel={(which==='query'?'查詢':'歷史案例')+'一小時進場前背景'}/>:<p>此快照資料不足。</p>}</section>)}
  </div>
  <details className="cw-chart-help"><summary>圖表與計算說明</summary><p className="fine">只以進場前盤面檢索；歷史後續不參與相似排名，也沒有繪製查詢盤面的未來。完整持倉模式載入期間內來源可用K棒，未補休市或缺漏；舊快照或超過60日顯示上限時才保留首尾。金色時間間隔點不代表連續行情。固定後續從參考進場後首根完整五分棒開盤起算，與原單持倉時間分開。價格報酬依做多／做空方向調整，未扣交易成本。歷史來源為 HistData BID 專題參考盤面，原始時鐘未獨立核實。</p></details>
 </div>;
}
