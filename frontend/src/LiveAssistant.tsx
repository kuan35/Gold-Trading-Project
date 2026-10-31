import {buildDialogueMemory} from './dialogueMemory';
import {useEffect,useRef,useState,type FormEvent} from 'react';
import LiveVolumeAnalysis from './LiveVolumeAnalysis';
import type {Side} from './types';
import AssistantControl,{useAssistantSettings} from './AssistantControl';
import {selectionLabel} from './modelSettings';
import {isModelAnalysis,analysisLabel} from './assistantProvider';
import CaseComparison,{type CaseComparisonData} from './CaseComparison';
import CaseOutcomePanel from './CaseOutcomePanel';import DraftScenarioRisk from './DraftScenarioRisk';import type {OutcomeAnalysis} from './caseOutcomes';

export type MarketReply={message:string;provider:string;llm_status:string;model:string|null;requested_effort?:string|null;source:string;market_status:string;as_of_utc:string;quote_time_utc:string|null;snapshot_id?:string|null;query_as_of_utc?:number|null;analysis_mode?:string;case_comparison?:CaseComparisonData|null;outcome_analysis?:OutcomeAnalysis|null;
 sections:{title:string;text:string;fact_ids:string[];source?:'program'|'model'}[];followups:string[];evidence:{id:string;text:string;values:Record<string,string>}[];draft:null};
const stamp=(value:string|null)=>value?new Date(value).toLocaleString('zh-TW',{hour12:false})+'（台灣）':'未提供';
const factText=(fact:MarketReply['evidence'][number])=>fact.text.replace(/\{\{([a-z0-9_]+)\}\}/g,(_,key)=>fact.values[key]??'資料不足');

export function LiveAssistantReply({reply,onFollowup}:{reply:MarketReply;onFollowup?:(text:string)=>void}){
 const used=new Set(reply.sections.flatMap(section=>section.fact_ids));
 return <article className="live-assistant-reply">
  <div className="live-reply-meta"><strong>{isModelAnalysis(reply.provider)?`${analysisLabel(reply.provider)}${reply.llm_status==='partial_grounding'?'＋程式盤面解讀':' 盤面解讀'}`:'程式盤面解讀'}</strong><span>cTrader DEMO · XAUUSD · {reply.market_status==='FROZEN'?'草稿建立快照（非即時更新）':reply.market_status==='CURRENT'?'即時資料快照':'行情未就緒'}</span></div>
  <p className="fine">報價 {stamp(reply.quote_time_utc)} · 分析快照 {stamp(reply.as_of_utc)}{reply.model?` · ${selectionLabel(reply.model,reply.requested_effort)}`:''}</p>
  {reply.llm_status!=='ok'&&<p className="live-assistant-status" role="status">{reply.message.split('\n\n')[0]}</p>}
  {reply.sections.map((section,i)=><section key={i}><h3>{section.title}</h3><p>{section.text}</p></section>)}
  <LiveVolumeAnalysis reply={reply}/>
  {reply.case_comparison&&<CaseComparison key={reply.snapshot_id} comparison={reply.case_comparison} snapshotId={reply.snapshot_id??null}/>}
  {reply.outcome_analysis&&<><DraftScenarioRisk analysis={reply.outcome_analysis}/><CaseOutcomePanel analysis={reply.outcome_analysis} snapshotId={reply.snapshot_id??null}/></>}
  {!!reply.evidence.length&&<details className="live-assistant-evidence"><summary>查看數據依據與限制</summary><p className="fine">數值與引用由程式核對；文字解讀不代表已驗證預測。指標取已收棒，報價時間與棒收盤時間不同。</p>{reply.evidence.filter(f=>used.has(f.id)).map(f=><p key={f.id}><small>{f.id}</small> {factText(f)}</p>)}</details>}
  {onFollowup&&reply.market_status==='CURRENT'&&<div className="live-followups">{reply.followups.map(text=><button key={text} type="button" onClick={()=>onFollowup(text)}>{text}</button>)}</div>}
 </article>;
}

export default function LiveAssistant({side}:{side:Side}){
 const assistantSettings=useAssistantSettings();
 const [message,setMessage]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const [includeCases,setIncludeCases]=useState(true),[querySide,setQuerySide]=useState<Side>(side);
 const [messages,setMessages]=useState<{question:string;reply?:MarketReply;error?:string}[]>([]);
 const threadId=useRef(`live-${crypto.randomUUID()}`);
 const lock=useRef(false),request=useRef<AbortController|null>(null),bottom=useRef<HTMLDivElement>(null),latest=useRef<HTMLDivElement>(null);
 useEffect(()=>()=>{request.current?.abort();},[]);
 useEffect(()=>{if(messages.length){if(!busy)latest.current?.scrollIntoView({block:'start'});else bottom.current?.scrollIntoView({block:'nearest'});}},[messages.length,busy]);
 const send=async(text:string)=>{
  if(lock.current||!text.trim())return;
  lock.current=true;setBusy(true);setError('');setMessage('');
  const index=messages.length,previous_questions=messages.slice(-4).map(m=>m.question.slice(0,600));
  setMessages(items=>[...items,{question:text}]);request.current=new AbortController();
  const timer=window.setTimeout(()=>request.current?.abort(),180000);
  try{
   const response=await fetch('/api/assistant/live-chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:text,llm_enabled:true,...assistantSettings.requestOptions,previous_questions,conversation_id:threadId.current,conversation:buildDialogueMemory(messages,threadId.current),side:querySide,include_cases:includeCases}),signal:request.current.signal});
   const result=await response.json();if(!response.ok)throw Error(typeof result.detail==='string'?result.detail:'即時盤面分析失敗');
   setMessages(items=>items.map((item,i)=>i===index?{...item,reply:result}:item));
  }catch(e){if(request.current?.signal.aborted)setError('分析逾時或已取消，可重新提問；沒有送出交易。');else setError(e instanceof Error?e.message:'無法取得盤面說明');}
  finally{window.clearTimeout(timer);lock.current=false;setBusy(false);}
 };
 return <div className="live-assistant" aria-label="即時盤面對話助手">
  <div className="live-assistant-controls"><strong>即時盤面助手</strong><span>cTrader DEMO · 五分／十五分／一小時</span>
   <AssistantControl settings={assistantSettings} busy={busy}/>
   <label><input type="checkbox" checked={includeCases} disabled={busy} onChange={event=>setIncludeCases(event.target.checked)}/>同時檢索歷史案例</label><label>案例比較方向<select aria-label="案例比較方向" value={querySide} disabled={busy} onChange={e=>setQuerySide(e.target.value as Side)}><option value="BUY">BUY 做多</option><option value="SELL">SELL 做空</option></select></label>
  </div>
  <div className="live-assistant-conversation" role="log" aria-live="polite">
   {!messages.length&&<div className="live-assistant-intro"><h2>看懂現在的黃金盤面</h2><p>直接問走勢、指標或價位；每次提問都重新讀取券商資料，回答附快照時間。</p><div className="live-followups">{['分析目前黃金盤面','一小時趨勢如何？','附近支撐壓力在哪？'].map(text=><button type="button" key={text} disabled={busy} onClick={()=>void send(text)}>{text}</button>)}</div></div>}
   {messages.map((item,i)=><div key={i} ref={i===messages.length-1?latest:undefined}><div className="chat-message user"><span>你 · 即時盤面</span><p>{item.question}</p></div>{item.reply&&<LiveAssistantReply reply={item.reply} onFollowup={busy?undefined:text=>void send(text)}/>}</div>)}
   {busy&&<p role="status" className="live-assistant-working">正在讀取盤面與整理回答…</p>}<div ref={bottom}/>
  </div>
  {error&&<p role="alert" className="modal-error">{error}</p>}
  <form className="chat-input" onSubmit={(event:FormEvent)=>{event.preventDefault();void send(message);}}><label htmlFor="live-message" className="sr-only">詢問即時盤面</label><textarea id="live-message" value={message} onChange={event=>setMessage(event.target.value)} maxLength={1500} rows={3} placeholder="例如：五分鐘偏空，為什麼一小時還偏多？"/><button className="primary" disabled={busy||!message.trim()}>{busy?'整理中…':'送出盤面問題'}</button></form>
 </div>;
}
