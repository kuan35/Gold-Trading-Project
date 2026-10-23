import {useEffect,useRef,useState,type FormEvent,type CSSProperties} from 'react';
import {api} from './api';import type {Side} from './types';import type {DemoMarket} from './demoMarket';import type {MarketReply} from './LiveAssistant';
import ConversationResize from './ConversationResize';import {CHAT_HEIGHT_KEY,savedChatHeight} from './chatSize';
import ConversationHelp from './ConversationHelp';import {nearChatBottom,turnScrollTarget} from './conversationScroll';
import SharedTicket from './SharedTicket';import ConversationReply from './ConversationReply';import ConversationCharts from './ConversationCharts';import ConversationOrderReview,{type CheckedOrder} from './ConversationOrderReview';
import {emptyInput,patchInput,missingInput,acceptRevision,discussionSide,type InputPatch} from './conversationState';
import {DESK_HISTORY_KEY,decodeArchive,encodeArchive,makeArchiveEntry,mergeArchive,needsAnalysis,changedFields,type ArchiveTurn,type ArchiveEntry} from './deskConversations';
import {DeskRail,DeskMarketHeader,DeskIcon} from './DeskChrome';
import DeskAccountTray from './DeskAccountTray';
type Interpretation={intent:string;analysis_side:Side|null;patch:InputPatch;proposal:InputPatch;message:string;missing_fields:string[];input_revision:number};
type Turn={id:number;question:string;note?:string;noteImportant?:boolean;reply?:MarketReply;proposal?:InputPatch;proposalRevision?:number;error?:string;record?:ArchiveTurn};
export default function ConversationWorkspace({market,light,visible,onHistory,onNavigate,onToggleTheme}:{market:DemoMarket|null;light:boolean;visible:boolean;onHistory:()=>void;onNavigate?:(view:'replay'|'live')=>void;onToggleTheme?:()=>void}){
 const [archive,setArchive]=useState(()=>{try{return decodeArchive(typeof localStorage==='undefined'?null:localStorage.getItem(DESK_HISTORY_KEY));}catch{return {items:[],writable:false,error:'此瀏覽器無法保存對話。'};}});
 const [threadId,setThreadId]=useState(()=>`chat-${Date.now()}`),[historyError,setHistoryError]=useState(''),[mobileTicket,setMobileTicket]=useState(false);
 const [chatShare,setChatShare]=useState<number|null>(null);const grid=useRef<HTMLDivElement>(null);
 const [chatHeight,setChatHeight]=useState<number|null>(()=>{try{return typeof localStorage==='undefined'?null:savedChatHeight(localStorage.getItem(CHAT_HEIGHT_KEY));}catch{return null;}});
 useEffect(()=>{try{if(chatHeight===null)localStorage.removeItem(CHAT_HEIGHT_KEY);else localStorage.setItem(CHAT_HEIGHT_KEY,String(chatHeight));}catch{}},[chatHeight]);
 const [showLatest,setShowLatest]=useState(false);
 const log=useRef<HTMLDivElement>(null),follow=useRef(true),lastSeen=useRef(0);
 const [input,setInput]=useState(emptyInput),[revision,setRevision]=useState(0),[turns,setTurns]=useState<Turn[]>([]),[text,setText]=useState('');
 const [enabled,setEnabled]=useState(false),[configured,setConfigured]=useState(false),[busy,setBusy]=useState(false),[checking,setChecking]=useState(false),[locked,setLocked]=useState(false),[error,setError]=useState('');
 const [checked,setChecked]=useState<{draft:CheckedOrder;revision:number}|null>(null),[inline,setInline]=useState(false),[chart,setChart]=useState<{id:string;mode:'analysis'|'cases';period?:'5m'|'15m'|'1h'}|null>(null);
 const inputRef=useRef(input),revisionRef=useRef(0),sideRef=useRef<Side|null>(null),lockedRef=useRef(false),working=useRef(false),checkWorking=useRef(false),checkedRef=useRef(checked),sequence=useRef(0),request=useRef<AbortController|null>(null),lastTurn=useRef<HTMLDivElement>(null),chartTrigger=useRef<HTMLElement|null>(null);
 useEffect(()=>{
  if(busy||!turns.length||turns.every(t=>t.record))return;
  const records=turns.filter(t=>t.record||t.reply||t.note||t.error).map(t=>t.record??{question:t.question,answer:[t.noteImportant||!t.reply?t.note:null,t.reply?.sections.slice(0,2).map(s=>s.text).join('\n'),t.error].filter(Boolean).join('\n'),at:t.reply?.as_of_utc??new Date().toISOString()});
  if(!records.length)return;
  setArchive(previous=>({...previous,items:mergeArchive(previous.items,makeArchiveEntry(threadId,records,Date.now()))}));
 },[turns,busy,threadId]);
 useEffect(()=>{if(!archive.writable||!archive.items.length)return;try{localStorage.setItem(DESK_HISTORY_KEY,encodeArchive(archive.items));}catch{setHistoryError('儲存空間不足，這次對話只保留在目前頁面。');}},[archive]);
 const openThread=(entry?:ArchiveEntry)=>{
  if(working.current||checkWorking.current||lockedRef.current)return;
  setTurns(entry?entry.turns.map(record=>({id:++sequence.current,question:record.question,record})):[]);
  setThreadId(entry?.id??`chat-${Date.now()}`);setText('');setChart(null);sideRef.current=null;follow.current=true;setShowLatest(false);
 };
 inputRef.current=input;checkedRef.current=checked;
 useEffect(()=>{let active=true;void api<{configured:boolean;enabled:boolean}>('/assistant/status').then(v=>{if(active)setConfigured(v.configured&&v.enabled);}).catch(()=>{});return()=>{active=false;request.current?.abort();};},[]);
 const setLock=(v:boolean)=>{lockedRef.current=v;setLocked(v);};
 const patch=(p:InputPatch)=>{
  if(lockedRef.current)return;const next=patchInput(inputRef.current,p);if(JSON.stringify(next)===JSON.stringify(inputRef.current))return;
  inputRef.current=next;revisionRef.current+=1;setRevision(revisionRef.current);setInput(next);setError('');
  const previous=checkedRef.current;if(previous){setChecked(null);checkedRef.current=null;void api(`/broker/drafts/${previous.draft.id}/cancel`,{}).catch(()=>{});}
 };
 const annotate=(id:number,part:Partial<Turn>)=>setTurns(items=>items.map(t=>t.id===id?{...t,...part}:t));
 const send=async(question:string,forcedSide?:Side)=>{
  if(working.current||!question.trim())return;working.current=true;setBusy(true);setError('');setText('');
  const id=++sequence.current,sentRevision=revisionRef.current;setTurns(v=>[...v,{id,question}]);
  const controller=new AbortController();request.current=controller;const timeout=window.setTimeout(()=>controller.abort(),60000);
  const post=async<T,>(path:string,body:unknown):Promise<T>=>{const r=await fetch('/api'+path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),signal:controller.signal});const v=await r.json().catch(()=>null);if(!r.ok||v===null)throw Error(typeof v?.detail==='string'?v.detail:'盤面服務暫時無法回覆，請稍後再試。');return v;};
  try{
   const interpretation=await post<Interpretation>('/assistant/interpret',{message:question,draft:inputRef.current,analysis_side:forcedSide??sideRef.current,input_revision:sentRevision});
   const stale=!acceptRevision(interpretation.input_revision,revisionRef.current);
   const before={...inputRef.current};
   if(!stale&&Object.keys(interpretation.patch).length){patch(interpretation.patch);}
   annotate(id,{noteImportant:stale||['CLARIFY','UNSUPPORTED','PREPARE','EDIT'].includes(interpretation.intent),note:stale?'欄位已在解析期間變更，本次沒有套用文字修改。':interpretation.message,proposal:!stale&&interpretation.intent==='DISCUSS'&&Object.keys(interpretation.proposal).length?interpretation.proposal:undefined,proposalRevision:revisionRef.current});
   if(interpretation.intent==='CLARIFY'||interpretation.intent==='UNSUPPORTED')return;
   const side=discussionSide(forcedSide??interpretation.analysis_side,inputRef.current.side,sideRef.current);sideRef.current=side;
   if(!needsAnalysis(interpretation.intent,interpretation.patch,before.side,side,turns.some(t=>Boolean(t.reply)))){
    if(interpretation.intent==='EDIT'||interpretation.intent==='PREPARE')annotate(id,{noteImportant:true,note:stale?'欄位已在解析期間變更，本次沒有套用文字修改。':`${changedFields(before,inputRef.current).join('；')||interpretation.message}。請重新檢查委託。`});
    return;
   }
   const safeQuestion=['PREPARE','EDIT'].includes(interpretation.intent)?`分析${side==='BUY'?'做多':side==='SELL'?'做空':''}想法的盤面支持、相反訊號與案例差異。`:question;
   const reply=await post<MarketReply>('/assistant/live-chat',{message:safeQuestion,llm_enabled:enabled,previous_questions:turns.slice(-4).map(t=>t.question.slice(0,600)),...(side?{side}:{}),include_cases:Boolean(side)});
   annotate(id,{reply});
  }catch(e){annotate(id,{error:controller.signal.aborted?'分析逾時或已取消，請重試。':e instanceof Error?e.message:'盤面分析失敗。'});}
  finally{window.clearTimeout(timeout);working.current=false;setBusy(false);}
 };
 const edit=(p:InputPatch)=>{const previous=inputRef.current.side;patch(p);if(p.side&&p.side!==previous&&!working.current)void send(p.side==='BUY'?'我想討論做多的盤面與案例':'我想討論做空的盤面與案例',p.side);};
 const check=async()=>{
  if(checkWorking.current||lockedRef.current)return;
  const sent=revisionRef.current,v={...inputRef.current};const missing=missingInput(v);if(missing.length){setInline(true);setError('請先填寫：'+missing.join('、'));return;}
  checkWorking.current=true;setChecking(true);setError('');
  try{
   const previous=checkedRef.current;if(previous){await api(`/broker/drafts/${previous.draft.id}/cancel`,{});setChecked(null);checkedRef.current=null;}
   const draft=await api<CheckedOrder>('/broker/drafts',{...v,limit_price:v.order_type==='LIMIT'?v.limit_price:null,sl:v.sl.trim()||null,tp:v.tp.trim()||null,retrieval_method:'context_contract_v1'});
   if(!acceptRevision(sent,revisionRef.current)){await api(`/broker/drafts/${draft.id}/cancel`,{});setError('欄位已變更，舊檢查已取消。請用最新欄位重新檢查。');return;}
   const next={draft,revision:sent};setChecked(next);checkedRef.current=next;
   const id=++sequence.current;setTurns(t=>[...t,{id,question:'檢查目前委託',noteImportant:true,note:'委託已檢查，請核對右側風險與確認結果。'}]);
  }catch(e){setError(e instanceof Error?e.message:'委託檢查失敗');}finally{checkWorking.current=false;setChecking(false);}
 };
 const jumpToLatest=()=>{const host=log.current,turn=lastTurn.current;if(host&&turn){host.scrollTo({top:turnScrollTarget(host.scrollTop,host.getBoundingClientRect().top,turn.getBoundingClientRect().top)});follow.current=true;setShowLatest(false);}};
 useEffect(()=>{if(!visible||!turns.length)return;const fresh=lastSeen.current!==turns.length;lastSeen.current=turns.length;if(fresh||follow.current)jumpToLatest();else if(!busy)setShowLatest(true);},[turns.length,busy,visible]);
 const latest=[...turns].reverse().find(t=>t.reply)?.reply;
 const quoteTime=Date.parse(market?.quote.source_time_utc??'')/1000,newBar=Boolean(latest?.query_as_of_utc&&Number.isFinite(quoteTime)&&Math.floor(quoteTime/300)*300>latest.query_as_of_utc);
 const ready=Boolean(market?.environment==='demo'&&market.order_connection&&market.quote.status==='CURRENT'&&market.account?.status==='CURRENT');
 const missing=missingInput(input);
 return <main id={visible?'market-workspace':undefined} className="conversation-workspace pd-workbench" hidden={!visible} tabIndex={-1} aria-label="聊天交易工作台">
  <DeskRail entries={archive.items} activeId={threadId} busy={busy||checking||locked} error={historyError||archive.error} onOpen={openThread} onNew={()=>openThread()} onNavigate={view=>onNavigate?.(view)}/>
  <div className="pd-body"><DeskMarketHeader market={market} light={light} onToggleTheme={()=>onToggleTheme?.()}/>
  <div className="cw-heading"><div><span className="pd-eyebrow">YOUR TRADING WORKSPACE</span><h1>交易對話</h1></div><button className="pd-ticket-toggle" type="button" aria-expanded={mobileTicket} aria-controls="pd-ticket" onClick={()=>setMobileTicket(!mobileTicket)}>{mobileTicket?'收合委託':'準備中委託'}</button></div>
  <div className="cw-grid" ref={grid} style={chatShare===null?undefined:{'--cw-chat-weight':`${chatShare}fr`,'--cw-ticket-weight':`${100-chatShare}fr`} as CSSProperties}><section className="cw-conversation" aria-label="交易對話"><div className="cw-chat-toolbar"><label><input type="checkbox" checked={enabled} disabled={!configured||busy} onChange={e=>setEnabled(e.target.checked)}/>啟用 Groq 白話解讀</label>{!configured&&<span className="fine">Groq 未連線</span>}<button type="button" disabled={busy} onClick={()=>void send('更新目前盤面與案例')}>{newBar?'有新收盤 · 更新分析':'更新盤面'}</button></div>
   <div className="cw-transcript"><div id="conversation-log" style={chatHeight===null?undefined:{height:chatHeight}} className="cw-log" ref={log} role="log" aria-label="聊天紀錄" aria-live="polite" aria-relevant="additions text" tabIndex={0} onScroll={()=>{const el=log.current;if(el){follow.current=nearChatBottom(el.scrollHeight,el.clientHeight,el.scrollTop);setShowLatest(!follow.current&&Boolean(lastTurn.current&&lastTurn.current.getBoundingClientRect().top>el.getBoundingClientRect().top+32));}}}>{!turns.length&&<div className="cw-welcome"><h2>先聊聊你的交易想法</h2><p>說出多空方向，就能一起看盤面依據與歷史案例。委託欄位也可以在對話中點選。</p><div className="cw-actions">{['我想做多，現在有哪些支持與相反訊號？','如果做空，有類似案例嗎？','附近支撐壓力在哪？'].map(q=><button type="button" key={q} onClick={()=>void send(q)}>{q}</button>)}</div></div>}
    {turns.map((t,i)=><div key={t.id} ref={i===turns.length-1?lastTurn:undefined} className="cw-turn"><div className="cw-user"><small>你</small><p>{t.question}</p></div>{t.record&&<div className="pd-archived"><small>歷史文字紀錄 · {new Date(t.record.at).toLocaleString('zh-TW')} · 不套用到委託</small><p>{t.record.answer}</p></div>}{t.note&&(t.noteImportant||!t.reply)&&<p className="cw-note">{t.note}</p>}{t.proposal&&<button type="button" disabled={locked||revision!==t.proposalRevision} onClick={()=>{patch(t.proposal!);setInline(true);annotate(t.id,{proposal:undefined,noteImportant:true,note:'已套用到準備中委託。'});}}>套用到草稿{revision!==t.proposalRevision?'（欄位已更新，請重新討論）':''}</button>}{t.reply&&<ConversationReply reply={t.reply} question={t.question} onChart={(mode,period)=>{if(t.reply?.snapshot_id){chartTrigger.current=document.activeElement instanceof HTMLElement?document.activeElement:null;setChart({id:t.reply.snapshot_id,mode,period});}}}/>}{t.error&&<p role="alert">{t.error}</p>}</div>)}
    {busy&&<p role="status">正在整理盤面與案例…</p>}
   </div>
   {showLatest&&<button type="button" className="cw-latest" onClick={jumpToLatest}>回到最新對話 ↓</button>}</div>
   <div className="cw-size-row"><ConversationResize axis="height" value={chatHeight} target={log} onChange={setChatHeight}/><button type="button" onClick={()=>{setChatHeight(null);setChatShare(null);}}>還原大小</button></div>
   <details className="cw-inline" open={inline} onToggle={e=>setInline(e.currentTarget.open)}><summary>在對話內填寫委託</summary><SharedTicket id="chat-ticket" value={input} onPatch={edit} disabled={locked}/></details>
   {chart&&<ConversationCharts key={chart.id+chart.mode+chart.period} initialPeriod={chart.period} reference={input} snapshotId={chart.id} mode={chart.mode} light={light} onClose={()=>{setChart(null);chartTrigger.current?.focus();}}/>}
   <form className="cw-composer" onSubmit={(e:FormEvent)=>{e.preventDefault();void send(text);}}><label className="sr-only" htmlFor="conversation-message">輸入交易想法或委託條件</label><textarea id="conversation-message" rows={2} maxLength={1500} value={text} onChange={e=>setText(e.target.value)} placeholder="和 Gold Desk 討論，或輸入下單條件…"/><button className="primary" aria-label="送出對話" disabled={busy||!text.trim()}><DeskIcon name="arrow"/><span>{busy?'整理中…':'送出'}</span></button></form>
  </section><ConversationResize axis="width" value={chatShare} target={grid} onChange={setChatShare}/><aside id="pd-ticket" className={`cw-sidebar ${mobileTicket?'pd-ticket-open':''}`} aria-label="準備中委託"><header><h2>準備中委託</h2><small>cTrader DEMO</small></header><SharedTicket id="side-ticket" value={input} onPatch={edit} disabled={locked}/>
   <button type="button" className="primary full" disabled={checking||locked||!ready} onClick={()=>void check()}>{checking?'讀取最新盤面並核對…':'檢查 DEMO 委託'}</button><p className="fine">{!ready?'等待最新 DEMO 報價與帳戶連線。':missing.length?'待填：'+missing.join('、'):'檢查後仍須由你按下確認。'}</p>
   {error&&<p role="alert" className="modal-error">{error}</p>}{checked&&<ConversationOrderReview key={checked.draft.id} draft={checked.draft} checkedRevision={checked.revision} currentRevision={revision} accountUpdated={market?.account?.updated_at_utc} onClear={()=>{setChecked(null);checkedRef.current=null;setLock(false);}} onLock={setLock} onHistory={onHistory}/>}
   <div className="cw-account"><strong>DEMO 帳戶摘要</strong><dl><div><dt>淨值</dt><dd>{market?.account?.status==='CURRENT'&&market.account.pnl_status==='CURRENT'?market.account.equity:'—'} {market?.account?.currency??''}</dd></div><div><dt>黃金浮動損益</dt><dd>{market?.account?.status==='CURRENT'&&market.account.pnl_status==='CURRENT'?market.account.xau_net_unrealized_pnl??'—':'—'} {market?.account?.currency??''}</dd></div></dl><button type="button" onClick={onHistory}>查看持倉與下單紀錄</button></div>
  </aside></div>
  {visible&&<DeskAccountTray market={market}/>}<ConversationHelp/></div>
 </main>;
}
