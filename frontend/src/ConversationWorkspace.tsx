import {AgentOrb,AgentTopbar,RAIL_EVENT} from './experience/AgentDesk';
import AgentDrawer,{type DrawerTab} from './experience/AgentDrawer';
import AgentAnswer from './experience/AgentAnswer';
import AssistantSettings from './experience/AssistantSettings';
import ConversationHistoryActions from './ConversationHistoryActions';
import type {ComparisonSelection} from './caseComparisonData';
import {useEffect,useRef,useState,type FormEvent,type CSSProperties} from 'react';
import {api} from './api';import type {Side} from './types';import type {DemoMarket} from './demoMarket';import type {MarketReply} from './LiveAssistant';
import ConversationResize from './ConversationResize';import {CHAT_HEIGHT_KEY,savedChatHeight} from './chatSize';
import ConversationHelp from './ConversationHelp';import {nearChatBottom,turnScrollTarget} from './conversationScroll';
import TicketCheckAction from './TicketCheckAction';
import SharedTicket from './SharedTicket';import ConversationReply from './ConversationReply';import ConversationCharts from './ConversationCharts';import ConversationOrderReview,{type CheckedOrder} from './ConversationOrderReview';
import {emptyInput,patchInput,missingInput,acceptRevision,discussionSide,type InputPatch} from './conversationState';
import {DESK_HISTORY_KEY,decodeArchive,saveConversationArchive,makeArchiveEntry,mergeArchive,renameConversation,deleteConversation,needsAnalysis,changedFields,type ArchiveTurn,type ArchiveEntry,type ArchiveLoad} from './deskConversations';
import {archiveTurn} from './conversationArchive';
import ArchivedConversationReply from './ArchivedConversationReply';
import {ConversationSessions,normalizeArchivedChart,type ArchivedChart} from './analysisHistory';
import {persistConversationDeletion} from './deskConversations';
import {goldQuestionKind,requestsMacroContext} from './macroEventModel';
import {DeskRail,DeskMarketHeader,DeskIcon} from './DeskChrome';
import DeskAccountTray from './DeskAccountTray';
import AssistantControl,{useAssistantSettings} from './AssistantControl';
import {buildDialogueMemory} from './dialogueMemory';
type TicketOrigin='inline'|'side';
type Interpretation={intent:string;analysis_side:Side|null;patch:InputPatch;proposal:InputPatch;message:string;missing_fields:string[];input_revision:number};
type Turn={id:number;question:string;at?:string;note?:string;noteImportant?:boolean;reply?:MarketReply;proposal?:InputPatch;proposalRevision?:number;error?:string;record?:ArchiveTurn};
const newThreadId=()=>`chat-${globalThis.crypto?.randomUUID?.()??Date.now()+'-'+Math.random().toString(36).slice(2)}`;
export default function ConversationWorkspace({market,light,visible,onHistory,onNavigate,onToggleTheme,onBusyChange}:{market:DemoMarket|null;light:boolean;visible:boolean;onHistory:()=>void;onNavigate?:(view:'replay'|'live')=>void;onToggleTheme?:()=>void;onBusyChange?:(busy:boolean)=>void}){
 const assistantSettings=useAssistantSettings();
 const [drawer,setDrawer]=useState(true),[drawerTab,setDrawerTab]=useState<DrawerTab>('order'),[settingsOpen,setSettingsOpen]=useState(false);
 const historyDialog=useRef<HTMLDialogElement>(null),railRef=useRef<(command:string)=>void>(()=>{});
 useEffect(()=>{const rail=(event:Event)=>railRef.current((event as CustomEvent).detail);const settings=()=>setSettingsOpen(true);window.addEventListener(RAIL_EVENT,rail);window.addEventListener('gd:settings',settings);return()=>{window.removeEventListener(RAIL_EVENT,rail);window.removeEventListener('gd:settings',settings);};},[]);

 const [archive,setArchive]=useState<ArchiveLoad>(()=>{try{return decodeArchive(typeof localStorage==='undefined'?null:localStorage.getItem(DESK_HISTORY_KEY));}catch{return {items:[],writable:false,error:'此瀏覽器無法保存對話。'};}});
 const [threadId,setThreadId]=useState(()=>archive.activeId??archive.items[0]?.id??newThreadId()),[historyError,setHistoryError]=useState(''),[mobileTicket,setMobileTicket]=useState(false);
 const [chatShare,setChatShare]=useState<number|null>(null);const grid=useRef<HTMLDivElement>(null);
 const [chatHeight,setChatHeight]=useState<number|null>(()=>{try{return typeof localStorage==='undefined'?null:savedChatHeight(localStorage.getItem(CHAT_HEIGHT_KEY));}catch{return null;}});
 useEffect(()=>{try{if(chatHeight===null)localStorage.removeItem(CHAT_HEIGHT_KEY);else localStorage.setItem(CHAT_HEIGHT_KEY,String(chatHeight));}catch{}},[chatHeight]);
 const [showLatest,setShowLatest]=useState(false);
 const log=useRef<HTMLDivElement>(null),follow=useRef(true),lastSeen=useRef(0);
 const [input,setInput]=useState(emptyInput),[revision,setRevision]=useState(0),[turns,setTurns]=useState<Turn[]>(()=>archive.items.find(e=>e.id===threadId)?.turns.map((record,i)=>({id:-(i+1),question:record.question,at:record.at,record}))??[]),[text,setText]=useState('');
 const [busy,setBusy]=useState(false),[checking,setChecking]=useState(false),[locked,setLocked]=useState(false),[error,setError]=useState('');
 useEffect(()=>{onBusyChange?.(busy||checking||locked);},[busy,checking,locked,onBusyChange]);
 const [reviewOrigin,setReviewOrigin]=useState<TicketOrigin>('side'),[errorOrigin,setErrorOrigin]=useState<TicketOrigin>('side');
 const [checked,setChecked]=useState<{draft:CheckedOrder;revision:number}|null>(null),[inline,setInline]=useState(false),[chart,setChart]=useState<ArchivedChart|null>(()=>archive.items.find(e=>e.id===threadId)?.chart??null);
 const sessions=useRef(new ConversationSessions<Turn>()),currentChart=useRef(chart);
 const inputRef=useRef(input),revisionRef=useRef(0),sideRef=useRef<Side|null>(null),lockedRef=useRef(false),working=useRef(false),checkWorking=useRef(false),checkedRef=useRef(checked),sequence=useRef(0),request=useRef<AbortController|null>(null),lastTurn=useRef<HTMLDivElement>(null),chartTrigger=useRef<HTMLElement|null>(null);
 useEffect(()=>{
  if(!turns.length||turns.every(t=>t.record))return;
  const records=turns.map(archiveTurn);
  if(!records.length)return;
  setArchive(previous=>({...previous,items:mergeArchive(previous.items,makeArchiveEntry(threadId,records,Date.now()))}));
 },[turns,threadId]);
 useEffect(()=>{if(!archive.writable)return;try{setHistoryError(saveConversationArchive(localStorage,archive.items,threadId).error);}catch{setHistoryError('此瀏覽器無法保存對話；這次變更未儲存。');}},[archive,threadId]);
 const openThread=(entry?:ArchiveEntry)=>{
  if(working.current||checkWorking.current||lockedRef.current)return;
  if(entry?.id===threadId)return;
  sessions.current.save(threadId,turns,currentChart.current);
  const cached=entry?sessions.current.get(entry.id):undefined,nextChart=cached?.chart??entry?.chart??null;
  setTurns(cached?.turns??(entry?entry.turns.map(record=>({id:++sequence.current,question:record.question,at:record.at,record})):[]));
  setThreadId(entry?.id??newThreadId());setText('');setChart(nextChart);currentChart.current=nextChart;sideRef.current=null;follow.current=true;setShowLatest(false);
 };
 const rememberChart=(next:ArchivedChart|null,display=true)=>{
  currentChart.current=next;if(display)setChart(next);
  setArchive(previous=>{
   let item=previous.items.find(e=>e.id===threadId);
   if(!item){if(!turns.length)return previous;item=makeArchiveEntry(threadId,turns.map(archiveTurn),Date.now());}
   const {chart:old,...base}=item,normalized=normalizeArchivedChart(next,item.turns.flatMap(t=>t.analysis_ref?[t.analysis_ref]:[]));
   const updated={...base,...(normalized?{chart:normalized}:{})};
   if(JSON.stringify(updated)===JSON.stringify(item)&&previous.items.some(e=>e.id===threadId))return previous;
   return {...previous,items:[...previous.items.filter(e=>e.id!==threadId),updated].sort((a,b)=>b.updatedAt-a.updatedAt)};
  });
 };
 const showChart=(reply:MarketReply,mode:'analysis'|'cases',period?:'5m'|'15m'|'1h',selection?:ComparisonSelection)=>{
  if(!reply.snapshot_id)return;chartTrigger.current=document.activeElement instanceof HTMLElement?document.activeElement:null;
  rememberChart({id:reply.snapshot_id,analysis_ref:reply.analysis_ref,mode,period,selection});
 };
 const removeThread=(id:string)=>{
  if(working.current||checkWorking.current||lockedRef.current)return;
  const activeId=id===threadId?newThreadId():threadId;
  let cleanupRefs:string[]=[];
  try{if(archive.writable){const saved=persistConversationDeletion(localStorage,archive.items,id,activeId);cleanupRefs=saved.cleanupRefs;if(!saved.ok)setHistoryError(saved.error);}}
  catch{setHistoryError('刪除尚未儲存，原本機分析仍保留。');}
  sessions.current.delete(id);
  if(id===threadId){setTurns([]);setThreadId(activeId);setText('');setChart(null);currentChart.current=null;sideRef.current=null;}
  setArchive(v=>({...v,items:deleteConversation(v.items,id)}));
  for(const ref of cleanupRefs)void fetch('/api/assistant/analyses/'+ref,{method:'DELETE'}).then(r=>{if(!r.ok)throw Error();}).catch(()=>setError('聊天已移除，但本機分析副本未能刪除；請確認本機服務。'));
 };
 inputRef.current=input;checkedRef.current=checked;
 useEffect(()=>()=>{request.current?.abort();},[]);
 const setLock=(v:boolean)=>{lockedRef.current=v;setLocked(v);};
 const patch=(p:InputPatch)=>{
  if(lockedRef.current)return;const next=patchInput(inputRef.current,p);if(JSON.stringify(next)===JSON.stringify(inputRef.current))return;
  inputRef.current=next;revisionRef.current+=1;setRevision(revisionRef.current);setInput(next);setError('');
  const previous=checkedRef.current;if(previous){setChecked(null);checkedRef.current=null;void api(`/broker/drafts/${previous.draft.id}/cancel`,{}).catch(()=>{});}
 };
 const annotate=(id:number,part:Partial<Turn>)=>setTurns(items=>items.map(t=>t.id===id?{...t,...part}:t));
 const send=async(question:string,forcedSide?:Side)=>{
  if(working.current||!question.trim())return;working.current=true;setBusy(true);setError('');setText('');
  const id=++sequence.current,sentRevision=revisionRef.current;setTurns(v=>[...v,{id,question,at:new Date().toISOString()}]);
  const selectedOptions={...assistantSettings.requestOptions};
  const controller=new AbortController();request.current=controller;const timeout=window.setTimeout(()=>controller.abort(),180000);
  const post=async<T,>(path:string,body:unknown):Promise<T>=>{const r=await fetch('/api'+path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),signal:controller.signal});const v=await r.json().catch(()=>null);if(!r.ok||v===null)throw Error(typeof v?.detail==='string'?v.detail:'盤面服務暫時無法回覆，請稍後再試。');return v;};
  try{
   if(goldQuestionKind(question)){
    if(import.meta.env.MODE==='pages'){annotate(id,{error:'黃金知識與事件工具需啟動本機後端。'});return;}
    const reply=await post<MarketReply>('/assistant/gold-chat',{message:question,llm_enabled:true,...selectedOptions,conversation_id:threadId,conversation:buildDialogueMemory(turns,threadId)});
    annotate(id,{reply});return;
   }
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
   const reply=await post<MarketReply>('/assistant/live-chat',{message:safeQuestion,llm_enabled:true,...selectedOptions,conversation_id:threadId,conversation:buildDialogueMemory(turns,threadId),previous_questions:turns.slice(-4).map(t=>t.question.slice(0,600)),...(side?{side}:{}),include_cases:Boolean(side),include_macro:requestsMacroContext(question),draft:{...inputRef.current},input_revision:revisionRef.current});
   annotate(id,{reply});
  }catch(e){annotate(id,{error:controller.signal.aborted?'分析逾時或已取消，請重試。':e instanceof Error?e.message:'盤面分析失敗。'});}
  finally{window.clearTimeout(timeout);working.current=false;setBusy(false);}
 };
 const edit=(p:InputPatch)=>{const previous=inputRef.current.side;patch(p);if(p.side&&p.side!==previous&&!working.current)void send(p.side==='BUY'?'我想討論做多的盤面與案例':'我想討論做空的盤面與案例',p.side);};
 const check=async(origin:TicketOrigin)=>{
  if(checkWorking.current||lockedRef.current)return;
  setErrorOrigin(origin);
  const sent=revisionRef.current,v={...inputRef.current};const missing=missingInput(v);if(missing.length){setInline(true);setError('請先填寫：'+missing.join('、'));return;}
  checkWorking.current=true;setChecking(true);setError('');
  try{
   const previous=checkedRef.current;if(previous){await api(`/broker/drafts/${previous.draft.id}/cancel`,{});setChecked(null);checkedRef.current=null;}
   const draft=await api<CheckedOrder>('/broker/drafts',{...v,limit_price:v.order_type==='LIMIT'?v.limit_price:null,sl:v.sl.trim()||null,tp:v.tp.trim()||null,retrieval_method:'context_contract_v1',input_revision:sent});
   if(!acceptRevision(sent,revisionRef.current)){await api(`/broker/drafts/${draft.id}/cancel`,{});setError('欄位已變更，舊檢查已取消。請用最新欄位重新檢查。');return;}
   const next={draft,revision:sent};setChecked(next);checkedRef.current=next;setReviewOrigin(origin);
   const id=++sequence.current;setTurns(t=>[...t,{id,question:'檢查目前委託',at:new Date().toISOString(),reply:draft.analysis_reply,noteImportant:true,note:'委託已檢查，請核對委託內容與風險，再由你確認。'}]);
  }catch(e){setError(e instanceof Error?e.message:'委託檢查失敗');}finally{checkWorking.current=false;setChecking(false);}
 };
 const jumpToLatest=()=>{const host=log.current,turn=lastTurn.current;if(host&&turn){host.scrollTo({top:turnScrollTarget(host.scrollTop,host.getBoundingClientRect().top,turn.getBoundingClientRect().top)});follow.current=true;setShowLatest(false);}};
 useEffect(()=>{if(!visible||!turns.length)return;const fresh=lastSeen.current!==turns.length;lastSeen.current=turns.length;if(fresh||follow.current)jumpToLatest();else if(!busy)setShowLatest(true);},[turns.length,busy,visible]);
 const latest=[...turns].reverse().find(t=>t.reply)?.reply;
 const quoteTime=Date.parse(market?.quote.source_time_utc??'')/1000,newBar=Boolean(latest?.query_as_of_utc&&Number.isFinite(quoteTime)&&Math.floor(quoteTime/300)*300>latest.query_as_of_utc);
 const ready=Boolean(market?.environment==='demo'&&market.order_connection&&market.quote.status==='CURRENT'&&market.account?.status==='CURRENT');
 const missing=missingInput(input);
 const orderReview=checked&&<ConversationOrderReview key={checked.draft.id} draft={checked.draft} checkedRevision={checked.revision} currentRevision={revision} accountUpdated={market?.account?.updated_at_utc} onClear={()=>{setChecked(null);checkedRef.current=null;setLock(false);}} onLock={setLock} onHistory={()=>{setDrawer(true);setDrawerTab('records');}}/>;
 railRef.current=command=>{if(working.current||checkWorking.current||lockedRef.current)return;if(command==='new')openThread();else if(command==='history')historyDialog.current?.showModal();};
 const sideLabel=input.side==='BUY'?'做多':input.side==='SELL'?'做空':'尚未選方向';
 const chips=['我想做多，現在有哪些支持與相反訊號？','如果做空，有類似案例嗎？','最近有哪些總經事件會影響黃金？'];
 const openHistory=()=>{setDrawer(true);setDrawerTab('records');};
 return <main id={visible?'market-workspace':undefined} className={`conversation-workspace ag-desk ${drawer?'ag-with-drawer':''}`} hidden={!visible} tabIndex={-1} aria-label="聊天交易工作台">
  <div className="ag-main">
   <AgentTopbar market={market} light={light} onTheme={()=>onToggleTheme?.()} drawerOpen={drawer} onDrawer={()=>setDrawer(v=>!v)}/>
   <div className="ag-body" ref={grid} style={drawer&&chatShare!==null?{gridTemplateColumns:`minmax(0,${chatShare}fr) minmax(300px,${100-chatShare}fr)`}:undefined}>
    <section className="ag-center" aria-label="交易對話">
     <div className="ag-agent-head"><AgentOrb busy={busy||checking}/><div className="ag-agent-id"><strong>Gold Desk Agent</strong><small>{busy?'正在整理盤面與案例':checking?'正在核對委託':'交易對話'}</small></div>
      <div className="ag-head-tools"><AssistantSettings settings={assistantSettings} busy={busy} open={settingsOpen} onOpen={setSettingsOpen}/><button type="button" className="ag-ghost" disabled={busy} onClick={()=>void send('更新目前盤面與案例')}>{newBar?'有新收盤 · 更新':'更新盤面'}</button></div>
     </div>
     <div id="conversation-log" className="ag-log" ref={log} style={chatHeight===null?undefined:{flex:'0 1 auto',height:chatHeight,minHeight:180}} role="log" aria-label="聊天紀錄" aria-live="polite" aria-relevant="additions text" tabIndex={0} onScroll={()=>{const el=log.current;if(el){follow.current=nearChatBottom(el.scrollHeight,el.clientHeight,el.scrollTop);setShowLatest(!follow.current&&Boolean(lastTurn.current&&lastTurn.current.getBoundingClientRect().top>el.getBoundingClientRect().top+32));}}}>
      {!turns.length&&<div className="ag-welcome"><AgentOrb busy={false} size={88}/><h2>今天想怎麼交易黃金？</h2><p>說出你的想法，一起看即時盤面、歷史案例與本筆風險。</p><div className="ag-starters">{[['黃金交易新手要先了解什麼？','新手教學'],['我想做多，現在有哪些支持與相反訊號？','看多空訊號'],['如果做空，有類似案例嗎？','找相似案例'],['幫我準備買進 0.01 手','準備一筆委託']].map(([q,title])=><button type="button" key={q} onClick={()=>void send(q)}><strong>{title}</strong><span>{q}</span></button>)}</div></div>}
      {turns.map((t,i)=><div key={t.id} ref={i===turns.length-1?lastTurn:undefined} className="ag-turn"><div className="ag-user"><p>{t.question}</p></div>
       {t.record&&<ArchivedConversationReply record={t.record} light={light} onChart={showChart}/>}
       {t.note&&(t.noteImportant||!t.reply)&&<p className="ag-note">{t.note}</p>}
       {t.proposal&&<button type="button" className="ag-apply" disabled={locked||revision!==t.proposalRevision} onClick={()=>{patch(t.proposal!);setInline(true);setDrawer(true);setDrawerTab('order');annotate(t.id,{proposal:undefined,noteImportant:true,note:'已套用到準備中委託。'});}}>套用到草稿{revision!==t.proposalRevision?'（欄位已更新，請重新討論）':''}</button>}
       {t.reply&&<AgentAnswer reply={t.reply} question={t.question} light={light} currentRevision={revision} onChart={(mode,period,selection)=>showChart(t.reply!,mode,period,selection)}/>}
       {t.error&&<p className="ag-error" role="alert">{t.error}</p>}
      </div>)}
      {busy&&<div className="ag-thinking" role="status"><AgentOrb busy size={28}/><p>正在整理這次盤面、案例與回覆…</p></div>}
      {chart&&<div className="ag-chart-evidence"><ConversationCharts key={chart.id+chart.mode+chart.period+JSON.stringify(chart.selection)} selection={chart.selection} initialPeriod={chart.period} analysisRef={chart.analysis_ref} reference={input} onViewChange={view=>{if(currentChart.current)rememberChart({...currentChart.current,...view},false);}} snapshotId={chart.id} mode={chart.mode} light={light} onClose={()=>{rememberChart(null);chartTrigger.current?.focus();}}/></div>}
     </div>
     {showLatest&&<button type="button" className="ag-latest" onClick={jumpToLatest}>回到最新對話 ↓</button>}
     <div className="ag-size-row"><ConversationResize axis="height" value={chatHeight} target={log} onChange={setChatHeight}/><button type="button" onClick={()=>{setChatHeight(null);setChatShare(null);}}>還原大小</button></div>
     <div className="ag-dock"><details className="cw-inline" open={inline||(reviewOrigin==='inline'&&Boolean(checked))} onToggle={e=>setInline(e.currentTarget.open)}><summary><strong>準備中委託</strong>{sideLabel} · {input.lot?input.lot+' 手':'手數未填'} · {input.order_type==='LIMIT'?'限價 '+(input.limit_price||'未填'):input.order_type==='MARKET'?'市價':'單型未選'}<small>編輯委託</small></summary><div className="ag-inline-ticket"><SharedTicket id="chat-ticket" value={input} onPatch={edit} disabled={locked}/><TicketCheckAction id="chat-ticket-check" ready={ready} checking={checking} locked={locked} missing={missing} error={errorOrigin==='inline'?error:undefined} onCheck={()=>void check('inline')}/>{reviewOrigin==='inline'&&orderReview}</div></details>
      <div className="ag-chips">{chips.map(q=><button type="button" key={q} disabled={busy} onClick={()=>void send(q)}>{q}</button>)}</div>
      <form className="ag-composer" onSubmit={(e:FormEvent)=>{e.preventDefault();void send(text);}}><label className="sr-only" htmlFor="conversation-message">輸入交易想法或委託條件</label><textarea id="conversation-message" rows={1} maxLength={1500} value={text} onChange={e=>setText(e.target.value)} onKeyDown={e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.nativeEvent.isComposing){e.preventDefault();void send(text);}}} placeholder="和 Agent 說你的想法，例如「買進 0.02 手，停損 4020」"/><button className="ag-send" aria-label="送出對話" disabled={busy||!text.trim()}><DeskIcon name="arrow"/></button></form>
      {(historyError||archive.error)&&<p className="ag-error" role="alert">{historyError||archive.error}</p>}
     </div>
    </section>
    <AgentDrawer resizer={<ConversationResize axis="width" value={chatShare} target={grid} onChange={setChatShare}/>} open={drawer&&visible} tab={drawerTab} onTab={setDrawerTab} onClose={()=>setDrawer(false)} light={light} market={market} order={<><h2 className="ag-ticket-title">準備中委託 <small>cTrader DEMO</small></h2><SharedTicket id="side-ticket" value={input} onPatch={edit} disabled={locked}/><TicketCheckAction id="side-ticket-check" ready={ready} checking={checking} locked={locked} missing={missing} error={errorOrigin==='side'?error:undefined} onCheck={()=>void check('side')}/>{reviewOrigin==='side'&&orderReview}<p className="fine">先檢查，再核對本筆委託與風險。</p></>}/>
   </div>
  </div>
  <dialog ref={historyDialog} className="ag-history-dialog" aria-labelledby="ag-history-heading"><header><h2 id="ag-history-heading">對話紀錄</h2><button type="button" aria-label="關閉對話紀錄" onClick={()=>historyDialog.current?.close()}>×</button></header><div className="pd-history">{archive.items.length?archive.items.map(entry=><div className="pd-history-entry" key={entry.id}><button className="pd-history-open" type="button" disabled={busy||checking||locked} aria-pressed={entry.id===threadId} onClick={()=>{openThread(entry);historyDialog.current?.close();}}>{entry.title}<small>{new Date(entry.updatedAt).toLocaleString('zh-TW')}</small></button><ConversationHistoryActions entry={entry} busy={busy||checking||locked} onRename={(id,title)=>setArchive(v=>({...v,items:renameConversation(v.items,id,title)}))} onDelete={removeThread}/></div>):<p className="ag-empty">完成對話後會保存在這裡。</p>}</div><ConversationHelp/></dialog>
 </main>;
}
