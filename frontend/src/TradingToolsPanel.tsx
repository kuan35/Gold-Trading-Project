import {createContext,useCallback,useContext,useEffect,useId,useRef,useState,type FormEvent} from 'react';
import BrokerAccountPanel from './BrokerAccountPanel';
import Chart from './Chart';
import {useAssistantSettings} from './AssistantControl';
import type {DemoMarket} from './demoMarket';
import type {Bar} from './types';
import type {MarketReply} from './LiveAssistant';
import {analysisLabel,isModelAnalysis} from './assistantProvider';

type ToolsTab='plans'|'alerts'|'broker';
export type TradingEnvironment='demo'|'live';
type Props={market:DemoMarket|null;conversationId?:string;light?:boolean;active?:boolean;initialTab?:ToolsTab;onOpenThread?:(id:string)=>void;environment?:TradingEnvironment};
const PanelActivity=createContext(true);
// DEMO and LIVE keep separate plan journals and reminders behind separate routes.
const PanelEnvironment=createContext<TradingEnvironment>('demo');
export const tradingBase=(environment:TradingEnvironment='demo')=>environment==='live'?'/api/live/trading':'/api/trading';
type Adherence='UNKNOWN'|'YES'|'NO'|'PARTIAL';
type SavedPlan={id:string;draft_id:string;created_at_utc:string;updated_at_utc?:string;revision:number;note:string;
 review_note:string;adherence:Adherence;lesson:string;conversation_id?:string|null;side?:string;lot?:string;price?:string;sl?:string|null;tp?:string|null;
 draft?:Record<string,unknown>;analysis?:Partial<MarketReply>;charts?:{snapshot_id?:string;query?:Partial<Record<'5m'|'1h',Bar[]>>;cases?:Array<{ref:string;'5m'?:Bar[];'1h'?:Bar[];clock_status?:string;alignment?:string}>};
 receipt?:{status?:string;order_id?:string|null;position_id?:string|null}|null;
 broker_outcome?:{status:string;reason?:string;closing_deals?:Array<{id?:string;executed_at_utc?:string;lot?:string;realized_gross_pnl?:string|null;commission?:string|null;swap?:string|null}>}};
type Collection<T>={status:string;reason?:string;items:T[];total?:number;limit?:number;offset?:number};
type CalendarEvent={id:string;name:string;time_utc:string};
type Calendar={status:string;events:CalendarEvent[]};
type Alert={id:string;revision:number;name:string;kind:'PRICE'|'CLOSE_5M'|'EVENT';enabled:boolean;state:'ACTIVE'|'TRIGGERED'|'PAUSED';
 field?:'bid'|'ask';comparator?:'GTE'|'LTE';threshold?:string;event_id?:string;lead_minutes?:number;message?:string;triggered_at_utc?:string;conversation_id?:string|null};
type Alerts=Collection<Alert>&{events?:unknown[];monitor_running?:boolean;monitor_error?:string|null;monitoring_note?:string};
type AlertInput={name:string;kind:Alert['kind'];field?:'bid'|'ask';comparator?:'GTE'|'LTE';threshold?:string;event_id?:string;lead_minutes?:string};
const stamp=(value?:string|null)=>value?`${value.replace('T',' ').replace(/\.\d+(?=Z|[+-])/, '').replace(/\+00:00|Z$/,'')} UTC`:'未提供';
const description=(error:unknown)=>error instanceof Error?error.message:'資料讀取失敗，請確認本機服務。';

export class TradingRequestError extends Error{
 constructor(message:string,public status:number){super(message);}
}
export async function tradingRequest<T>(path:string,options:{method?:string;body?:unknown;signal?:AbortSignal;environment?:TradingEnvironment}={},fetcher:typeof fetch=fetch):Promise<T>{
 const response=await fetcher(tradingBase(options.environment)+path,{method:options.method??'GET',signal:options.signal,cache:'no-store',
  ...(options.body!==undefined?{headers:{'Content-Type':'application/json'},body:JSON.stringify(options.body)}:{})});
 const content=await response.json().catch(()=>({detail:'服務回應格式錯誤。'}));
 if(!response.ok)throw new TradingRequestError(typeof content.detail==='string'?content.detail:'操作失敗，請重新載入。',response.status);
 return content as T;
}
export const refreshTradingCalendar=(signal?:AbortSignal,fetcher:typeof fetch=fetch,environment:TradingEnvironment='demo')=>tradingRequest<Calendar>('/calendar?refresh=true',{signal,environment},fetcher);
export const planDiscussionLabel=(reply:Pick<MarketReply,'provider'|'model'>)=>isModelAnalysis(reply.provider)?`${analysisLabel(reply.provider)} 回顧${reply.model?` · ${reply.model}`:''}`:'程式回顧';

/** Cancel transport and ignore late replies even when a transport ignores abort. */
export class LatestTradingRequest{
 private current:AbortController|null=null;
 cancel(){this.current?.abort();this.current=null;}
 async run<T>(read:(signal:AbortSignal)=>Promise<T>,accept:(value:T)=>void,reject?:(error:unknown)=>void){
  this.cancel();const controller=new AbortController();this.current=controller;
  try{const value=await read(controller.signal);if(this.current===controller&&!controller.signal.aborted)accept(value);}
  catch(error){if(this.current===controller&&!controller.signal.aborted)reject?.(error);}
 }
}

type PollingEnvironment={page:Pick<Document,'hidden'|'addEventListener'|'removeEventListener'>;setTimer:(task:()=>void,delay:number)=>number;clearTimer:(id:number)=>void};
export function startTradingPolling<T>(read:(signal:AbortSignal)=>Promise<T>,accept:(value:T)=>void,reject:(error:unknown)=>void,
 environment:PollingEnvironment={page:document,setTimer:(task,delay)=>window.setTimeout(task,delay),clearTimer:id=>window.clearTimeout(id)},enabled=true){
 if(!enabled)return()=>{};
 let active=true,timer:number|undefined,version=0;const request=new LatestTradingRequest(),{page,setTimer,clearTimer}=environment;
 const refresh=async()=>{
  if(!active||page.hidden)return;const own=++version;
  await request.run(read,accept,reject);
  if(active&&own===version&&!page.hidden)timer=setTimer(()=>void refresh(),5000);
 };
 const visibility=()=>{version++;if(timer!==undefined)clearTimer(timer);timer=undefined;request.cancel();if(!page.hidden)void refresh();};
 page.addEventListener('visibilitychange',visibility);void refresh();
 return()=>{active=false;version++;if(timer!==undefined)clearTimer(timer);request.cancel();page.removeEventListener('visibilitychange',visibility);};
}

function useTradingCollection<T>(path:string){
 const active=useContext(PanelActivity),environment=useContext(PanelEnvironment);
 const [data,setData]=useState<T|null>(null),[error,setError]=useState(''),[cycle,setCycle]=useState(0);
 const refresh=useCallback(()=>setCycle(value=>value+1),[]);
 useEffect(()=>{if(!active)return;return startTradingPolling(signal=>tradingRequest<T>(path,{signal,environment}),value=>{setData(value);setError('');},error=>setError(description(error)));},[path,cycle,active,environment]);
 return {data,error,refresh,setData};
}

export function alertAvailability(market:DemoMarket|null,environment:TradingEnvironment='demo'):string{
 if(!market||market.source!==`ctrader_${environment}_xauusd`||market.environment!==environment)return `需要 cTrader ${environment.toUpperCase()} 行情，不能使用回放或另一個環境的資料建立提醒。`;
 if(market.connection_status!=='CONNECTED'||market.account?.status!=='CURRENT')return '券商未連線或帳戶未同步，暫不能建立提醒。';
 if(market.quote.status!=='CURRENT'||market.quote.age_seconds==null||market.quote.age_seconds<0||market.quote.age_seconds>5)return '行情已過期或未就緒，暫不能建立提醒。';
 return '';
}
export function alertRequest(input:AlertInput,conversationId?:string){
 const base={name:input.name.trim(),kind:input.kind,...(conversationId?{conversation_id:conversationId}:{})};
 if(input.kind==='EVENT')return {...base,event_id:input.event_id,lead_minutes:Number(input.lead_minutes??'15')};
 return {...base,field:input.kind==='CLOSE_5M'?'bid':input.field??'bid',comparator:input.comparator??'GTE',threshold:input.threshold??''};
}
export function planQueryBars(plan:SavedPlan,period:'5m'|'1h'):Bar[]{
 if(plan.charts?.snapshot_id&&plan.analysis?.snapshot_id&&plan.charts.snapshot_id!==plan.analysis.snapshot_id)return [];
 return plan.charts?.query?.[period]??[];
}

export function PlanEvidence({plan,light=false}:{plan:SavedPlan;light?:boolean}){
 const analysis=plan.analysis,comparison=analysis?.case_comparison;
 return <div className="trading-plan-evidence">
  <h4>當時理由</h4><p style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere'}}>{plan.note||'當時未填寫理由。'}</p>
  <p className="fine">計畫建立 {stamp(plan.created_at_utc)} · 當時分析 {stamp(analysis?.as_of_utc)}。以下固定保存，不更新成目前行情。</p>
  {analysis?.sections?.map((section,index)=><section key={index}><h4>{section.title}</h4><p style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere'}}>{section.text}</p></section>)}
  {!analysis?.sections?.length&&<p>當時未保存盤面段落。</p>}
  <p className="fine">案例：{comparison?.label??comparison?.status??'未保存案例狀態'}{comparison?.reason?` · ${comparison.reason}`:''}</p>
  {!!comparison?.cases?.length&&<details><summary>當時的案例與差異</summary>{comparison.cases.map(item=><section key={item.ref}><h4>{item.ref} · {item.event}</h4>{item.similarities.map((text,i)=><p key={'s'+i}>相近：{text}</p>)}{item.differences.map((text,i)=><p key={'d'+i}>差異：{text}</p>)}<FrozenCase plan={plan} caseRef={item.ref} light={light}/></section>)}</details>}
  <details><summary>查看當時五分／一小時 K 線</summary>{(['5m','1h'] as const).map(period=>{
   const bars=planQueryBars(plan,period);
   return <section key={period}><h4>{period==='5m'?'五分鐘':'一小時'} · 當時已保存盤面</h4>{bars.length?
    <div style={{height:280,maxHeight:280,minWidth:0}}><Chart bars={bars} light={light} ariaLabel={`交易計畫原始${period}盤面`} scope={`plan:${plan.id}:${analysis?.snapshot_id??''}:${period}`}/></div>:
    <p className="fine">當時圖表未保存或快照不一致；不補用目前行情。</p>}</section>;
  })}</details>
  {plan.broker_outcome&&<details><summary>券商平倉證據</summary><p className="fine">{plan.broker_outcome.reason}</p>
   {plan.broker_outcome.closing_deals?.map((deal,index)=><p key={deal.id??index}>{stamp(deal.executed_at_utc)} · {deal.lot??'—'} 手 · 毛損益 {deal.realized_gross_pnl??'未知'} · 佣金 {deal.commission??'未知'} · 隔夜費 {deal.swap??'未知'}</p>)}
   {!plan.broker_outcome.closing_deals?.length&&<p className="fine">尚無可確認的關聯平倉成交。</p>}</details>}
 </div>;
}

function FrozenCase({plan,caseRef,light}:{plan:SavedPlan;caseRef:string;light:boolean}){
 const [open,setOpen]=useState(false),row=plan.charts?.cases?.find(c=>c.ref===caseRef);
 return <details onToggle={e=>setOpen(e.currentTarget.open)}><summary>原始案例 K 線</summary>{open&&row&&(['5m','1h'] as const).map(period=><section key={period}><h4>{period==='5m'?'五分鐘':'一小時'} · 歷史參考盤面</h4>{row[period]?.length?<div style={{height:280,maxHeight:280,minWidth:0}}><Chart bars={row[period]!} light={light} scope={`plan:${plan.id}:${caseRef}:${period}`} ariaLabel={`計畫保存${caseRef}${period}歷史參考盤面`}/></div>:<p>當時未保存此週期。</p>}</section>)}{open&&<p className="fine">依當時來源時間模型保存；原始時鐘狀態 {row?.clock_status??'UNKNOWN'}。</p>}</details>;
}

function PlanReview({plan,onReload,onSaved}:{plan:SavedPlan;onReload:()=>void;onSaved:(plan:SavedPlan)=>void}){
 const [note,setNote]=useState(plan.review_note??''),[adherence,setAdherence]=useState<Adherence>(plan.adherence??'UNKNOWN'),[lesson,setLesson]=useState(plan.lesson??'');
 const [revision,setRevision]=useState(plan.revision);
 const [busy,setBusy]=useState(false),[error,setError]=useState(''),[conflict,setConflict]=useState(false),[saved,setSaved]=useState(false);
 const request=useRef(new LatestTradingRequest()),lock=useRef(false),environment=useContext(PanelEnvironment);
 useEffect(()=>()=>request.current.cancel(),[]);
 const save=(event:FormEvent)=>{
  event.preventDefault();if(lock.current||conflict)return;lock.current=true;setBusy(true);setSaved(false);setError('');
  void request.current.run(signal=>tradingRequest<SavedPlan>(`/plans/${encodeURIComponent(plan.id)}/review`,{method:'PATCH',body:{revision,note,adherence,lesson},signal,environment}),
   value=>{lock.current=false;setBusy(false);setRevision(value.revision);setSaved(true);onSaved(value);},error=>{lock.current=false;setBusy(false);setError(description(error));setConflict(error instanceof TradingRequestError&&error.status===409);});
 };
 return <form onSubmit={save} className="trading-plan-review"><h4>事後復盤</h4><p className="fine">此處不改寫當時理由或分析。</p>
  <label>復盤筆記<textarea aria-label="復盤筆記" rows={3} maxLength={10000} disabled={busy||conflict} value={note} onChange={e=>{setNote(e.target.value);setSaved(false);}}/></label>
  <label>是否遵守計畫<select aria-label="是否遵守計畫" disabled={busy||conflict} value={adherence} onChange={e=>{setAdherence(e.target.value as Adherence);setSaved(false);}}><option value="UNKNOWN">尚未判斷</option><option value="YES">有遵守</option><option value="NO">未遵守</option><option value="PARTIAL">部分遵守</option></select></label>
  <label>心得<textarea aria-label="復盤心得" rows={2} maxLength={10000} disabled={busy||conflict} value={lesson} onChange={e=>{setLesson(e.target.value);setSaved(false);}}/></label>
  <button disabled={busy||conflict}>{busy?'儲存中…':'儲存復盤'}</button>{saved&&<p role="status">復盤已儲存。</p>}
  {error&&<p role="alert">{error}</p>}{conflict&&<><p className="fine">版本已變更，請重新載入後再編輯，避免覆蓋其他復盤。</p><button type="button" onClick={onReload}>重新載入計畫</button></>}
 </form>;
}

function PlanDiscussion({plan}:{plan:SavedPlan}){
 const active=useContext(PanelActivity),environment=useContext(PanelEnvironment);
 const settings=useAssistantSettings(),[message,setMessage]=useState(''),[reply,setReply]=useState<MarketReply|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const request=useRef(new LatestTradingRequest()),lock=useRef(false);
 useEffect(()=>{const cancel=()=>{if(document.hidden){request.current.cancel();lock.current=false;setBusy(false);}};document.addEventListener('visibilitychange',cancel);return()=>{request.current.cancel();document.removeEventListener('visibilitychange',cancel);};},[]);
 useEffect(()=>{if(!active){request.current.cancel();lock.current=false;setBusy(false);}},[active]);
 const modelReady=(settings.selection.provider??settings.status?.provider??'program')!=='program'&&Boolean(settings.status?.configured&&settings.status.enabled);
 const send=(event:FormEvent)=>{
  event.preventDefault();if(!active||lock.current||!message.trim())return;lock.current=true;setBusy(true);setError('');setReply(null);
  const options=modelReady?settings.requestOptions:{provider:'program'};
  void request.current.run(signal=>tradingRequest<MarketReply>(`/plans/${encodeURIComponent(plan.id)}/discuss`,{method:'POST',body:{...options,message:message.trim(),llm_enabled:true},signal,environment}),
   value=>{lock.current=false;setBusy(false);setReply(value);},error=>{lock.current=false;setBusy(false);setError(description(error));});
 };
 return <details><summary>根據原始計畫繼續討論</summary><p className="fine">{modelReady?'按下回顧時使用目前選定的模型。':'目前使用程式回顧；模型未就緒或已選程式模式。'}只使用當時固定依據。</p>
  <form onSubmit={send}><label>回顧問題<textarea aria-label="交易計畫回顧問題" maxLength={1500} rows={2} value={message} onChange={e=>setMessage(e.target.value)}/></label><button disabled={busy||!message.trim()}>{busy?'回顧中…':'回顧原始計畫'}</button></form>
  {error&&<p role="alert">{error}</p>}{reply&&<article><p className="fine">{planDiscussionLabel(reply)} · 原始分析 {stamp(reply.as_of_utc)}</p>{reply.sections?.map((section,index)=><section key={index}><h4>{section.title}</h4><p style={{whiteSpace:'pre-wrap'}}>{section.text}</p></section>)}</article>}
 </details>;
}

function PlanDetail({id,light,onChanged,onOpenThread}:{id:string;light:boolean;onChanged:()=>void;onOpenThread?:Props['onOpenThread']}){
 const active=useContext(PanelActivity),environment=useContext(PanelEnvironment);
 const [plan,setPlan]=useState<SavedPlan|null>(null),[error,setError]=useState(''),[cycle,setCycle]=useState(0);
 useEffect(()=>{if(!active)return;setError('');const request=new LatestTradingRequest();void request.run(signal=>tradingRequest<SavedPlan>(`/plans/${encodeURIComponent(id)}`,{signal,environment}),setPlan,error=>setError(description(error)));return()=>request.cancel();},[id,cycle,active,environment]);
 if(error)return <p role="alert">{error} <button onClick={()=>setCycle(value=>value+1)}>重新載入</button></p>;
 if(!plan)return <p role="status">讀取原始計畫…</p>;
 return <div className="trading-plan-detail"><PlanEvidence plan={plan} light={light}/>
  {plan.conversation_id&&onOpenThread&&<button type="button" onClick={()=>onOpenThread(plan.conversation_id!)}>回原討論</button>}
  <PlanReview key={'review:'+plan.id} plan={plan} onReload={()=>{setPlan(null);setCycle(value=>value+1);}} onSaved={value=>{setPlan(current=>({...current,...value}));onChanged();}}/>
  <PlanDiscussion key={'discussion:'+plan.id} plan={plan}/></div>;
}

function PlansPanel({light,onOpenThread}:{light:boolean;onOpenThread?:Props['onOpenThread']}){
 const [offset,setOffset]=useState(0),[selected,setSelected]=useState<string|null>(null);
 const {data,error,refresh}=useTradingCollection<Collection<SavedPlan>>(`/plans?limit=20&offset=${offset}`);
 return <div><p className="fine">檢查委託時自動保存草稿與當時依據；刪聊天仍保留計畫。接受委託不等於已成交。</p>
  {error&&<p role="alert">{error}</p>}{data&&data.status!=='AVAILABLE'&&<p role="status">{data.reason??'帳戶資料尚未就緒。'}</p>}
  {!data&&!error&&<p role="status">讀取交易計畫…</p>}
  {data?.items.map(plan=><article key={plan.id}><button type="button" aria-expanded={selected===plan.id} onClick={()=>setSelected(selected===plan.id?null:plan.id)}>
   {plan.side==='BUY'?'買進':plan.side==='SELL'?'賣出':'計畫'} {plan.lot??'—'} 手 · {stamp(plan.created_at_utc)}</button>
   <p className="fine">進場 {plan.price??'—'} · SL {plan.sl??'未設定'} · TP {plan.tp??'未設定'} · {plan.receipt?.status??'尚未確認委託'}</p>
   {selected===plan.id&&<PlanDetail key={plan.id} id={plan.id} light={light} onChanged={refresh} onOpenThread={onOpenThread}/>}</article>)}
  {data?.status==='AVAILABLE'&&!data.items.length&&<p>尚無交易計畫。先填寫草稿並檢查委託，即可保存當時依據。</p>}
  {Boolean(data?.total)&&<div className="broker-history-pages"><button disabled={offset===0} onClick={()=>{setSelected(null);setOffset(Math.max(0,offset-20));}}>上一頁</button><span>共 {data?.total} 筆</span><button disabled={offset+20>=(data?.total??0)} onClick={()=>{setSelected(null);setOffset(offset+20);}}>下一頁</button></div>}
 </div>;
}

export function AlertEditor({reason,events,conversationId,onCreated}:{reason:string;events:CalendarEvent[];conversationId?:string;onCreated:()=>void}){
 const [name,setName]=useState(''),[kind,setKind]=useState<Alert['kind']>('PRICE'),[field,setField]=useState<'bid'|'ask'>('bid'),[comparator,setComparator]=useState<'GTE'|'LTE'>('GTE'),[threshold,setThreshold]=useState(''),[eventId,setEventId]=useState(''),[lead,setLead]=useState('15');
 const [busy,setBusy]=useState(false),[error,setError]=useState(''),[saved,setSaved]=useState(false),request=useRef(new LatestTradingRequest()),lock=useRef(false),environment=useContext(PanelEnvironment);
 useEffect(()=>()=>request.current.cancel(),[]);
 const create=(event:FormEvent)=>{event.preventDefault();if(lock.current||reason)return;lock.current=true;setBusy(true);setSaved(false);setError('');
  const body=alertRequest({name,kind,field,comparator,threshold,event_id:eventId,lead_minutes:lead},conversationId);
  void request.current.run(signal=>tradingRequest('/alerts',{method:'POST',body,signal,environment}),()=>{lock.current=false;setBusy(false);setSaved(true);onCreated();},error=>{lock.current=false;setBusy(false);setError(description(error));});};
 return <details><summary>建立條件提醒</summary><p className="fine">服務運行且資料有效時才監控，觸發一次；斷線不回補過去觸價。提醒不送單、不自動呼叫模型。</p>
  {reason&&<p role="status">{reason}</p>}<form onSubmit={create}><fieldset disabled={Boolean(reason)||busy} style={{minWidth:0}}>
   <label>名稱<input aria-label="提醒名稱" value={name} maxLength={120} required onChange={e=>setName(e.target.value)}/></label>
   <label>條件<select aria-label="提醒條件" value={kind} onChange={e=>setKind(e.target.value as Alert['kind'])}><option value="PRICE">即時價位</option><option value="CLOSE_5M">已收五分棒</option><option value="EVENT">官方事件提前提醒</option></select></label>
   {kind==='EVENT'?<><label>官方事件<select aria-label="官方事件" value={eventId} required onChange={e=>setEventId(e.target.value)}><option value="">選擇未來事件</option>{events.map(event=><option key={event.id} value={event.id}>{event.name} · {stamp(event.time_utc)}</option>)}</select></label><label>提前分鐘<input aria-label="事件提前分鐘" inputMode="numeric" value={lead} pattern="[0-9]+" required onChange={e=>setLead(e.target.value)}/></label>{!events.length&&<p className="fine">目前無可選的未來官方事件。</p>}</>:
    <><label>報價<select aria-label="提醒報價" value={kind==='CLOSE_5M'?'bid':field} disabled={kind==='CLOSE_5M'} onChange={e=>setField(e.target.value as 'bid'|'ask')}><option value="bid">Bid 賣出價</option><option value="ask">Ask 買進價</option></select></label><label>比較<select aria-label="提醒比較" value={comparator} onChange={e=>setComparator(e.target.value as 'GTE'|'LTE')}><option value="GTE">大於或等於</option><option value="LTE">小於或等於</option></select></label><label>黃金價位<input aria-label="提醒價位" inputMode="decimal" value={threshold} pattern="[0-9]+([.][0-9]+)?" required onChange={e=>setThreshold(e.target.value)}/></label></>}
   <button disabled={busy||!name.trim()||(kind==='EVENT'?!events.some(event=>event.id===eventId):!threshold.trim())}>{busy?'建立中…':'建立提醒'}</button>
  </fieldset></form>{error&&<p role="alert">{error}</p>}{saved&&<p role="status">提醒已建立。</p>}</details>;
}

function AlertItem({alert,onChanged,onOpenThread}:{alert:Alert;onChanged:()=>void;onOpenThread?:Props['onOpenThread']}){
 const [busy,setBusy]=useState(false),[error,setError]=useState(''),[deleting,setDeleting]=useState(false),request=useRef(new LatestTradingRequest()),lock=useRef(false),environment=useContext(PanelEnvironment);
 useEffect(()=>()=>request.current.cancel(),[]);
 const change=(remove=false)=>{if(lock.current)return;lock.current=true;setBusy(true);setError('');
  const path=`/alerts/${encodeURIComponent(alert.id)}`+(remove?`?revision=${alert.revision}`:'');
  void request.current.run(signal=>tradingRequest(path,{method:remove?'DELETE':'PATCH',...(remove?{}:{body:{revision:alert.revision,enabled:!(alert.enabled&&alert.state==='ACTIVE')}}),signal,environment}),()=>{lock.current=false;setBusy(false);setDeleting(false);onChanged();},error=>{lock.current=false;setBusy(false);setError(description(error));onChanged();});};
 const label=alert.state==='TRIGGERED'?'已觸發一次':alert.state==='PAUSED'?'已暫停':'已啟用';
 return <article><h4>{alert.name} · {label}</h4><p className="fine">{alert.kind==='EVENT'?`官方事件 · 提前 ${alert.lead_minutes??'—'} 分鐘`:`${alert.kind==='CLOSE_5M'?'已收五分棒 Bid':alert.field==='ask'?'Ask':'Bid'} ${alert.comparator==='LTE'?'≤':'≥'} ${alert.threshold??'—'}`}</p>
  {alert.message&&<p>{alert.message}</p>}{alert.triggered_at_utc&&<p className="fine">觸發 {stamp(alert.triggered_at_utc)}</p>}
  <button disabled={busy} onClick={()=>change()}>{alert.enabled&&alert.state==='ACTIVE'?'暫停':alert.state==='TRIGGERED'?'重新啟用':'啟用'}</button>
  <button disabled={busy} onClick={()=>setDeleting(value=>!value)}>刪除</button>{deleting&&<span>確定刪除此提醒？ <button disabled={busy} onClick={()=>change(true)}>確認刪除</button><button disabled={busy} onClick={()=>setDeleting(false)}>保留</button></span>}
  {alert.conversation_id&&onOpenThread&&<button onClick={()=>onOpenThread(alert.conversation_id!)}>回原討論</button>}{error&&<p role="alert">{error}</p>}
 </article>;
}

function AlertsPanel({market,conversationId,onOpenThread}:Omit<Props,'light'>){
 const active=useContext(PanelActivity),environment=useContext(PanelEnvironment);
 const {data,error,refresh}=useTradingCollection<Alerts>('/alerts'),calendar=useTradingCollection<Calendar>('/calendar');
 const [calendarBusy,setCalendarBusy]=useState(false),[calendarError,setCalendarError]=useState(''),calendarRequest=useRef(new LatestTradingRequest()),calendarLock=useRef(false);
 useEffect(()=>{if(!active){calendarRequest.current.cancel();calendarLock.current=false;setCalendarBusy(false);}return()=>calendarRequest.current.cancel();},[active]);
 const updateCalendar=()=>{if(!active||calendarLock.current)return;calendarLock.current=true;setCalendarBusy(true);setCalendarError('');void calendarRequest.current.run(signal=>refreshTradingCalendar(signal,fetch,environment),value=>{calendar.setData(value);calendar.refresh();calendarLock.current=false;setCalendarBusy(false);},error=>{setCalendarError(description(error));calendarLock.current=false;setCalendarBusy(false);});};
 const reason=alertAvailability(market,environment)||(data?.status!=='AVAILABLE'?(data?.reason??'提醒服務尚未就緒。'):'');
 const events=calendar.data&&['AVAILABLE','CURRENT','READY'].includes(calendar.data.status)?calendar.data.events.filter(event=>Date.parse(event.time_utc)>Date.now()):[];
 return <div><p className="fine">{data?.monitoring_note??'只有本機服務運行且行情連線時才會通知；提醒不會下單。'}</p>
  {data?.monitor_running===false&&<p role="status">監控服務未運行；不代表持續監控中。</p>}{data?.monitor_error&&<p role="alert">{data.monitor_error}</p>}
  {error&&<p role="alert">{error}</p>}<button type="button" disabled={!active||calendarBusy} onClick={updateCalendar}>{calendarBusy?'更新事件中…':'更新官方事件'}</button>
  {calendarError&&<p role="alert">{calendarError}</p>}<AlertEditor reason={reason} events={events} conversationId={conversationId} onCreated={refresh}/>
  {calendar.error&&<p role="status">官方事件清單暫時無法讀取。</p>}
  {data?.items.map(alert=><AlertItem key={`${alert.id}:${alert.revision}`} alert={alert} onChanged={refresh} onOpenThread={onOpenThread}/>)}
  {data?.status==='AVAILABLE'&&!data.items.length&&<p>尚無條件提醒。可設定價位、五分收盤或官方事件。</p>}
 </div>;
}

export default function TradingToolsPanel({market,conversationId,light=false,active=true,initialTab='plans',onOpenThread,environment='demo'}:Props){
 const [tab,setTab]=useState<ToolsTab>(initialTab),[visited,setVisited]=useState<ToolsTab[]>([initialTab]),id=useId();
 const open=useCallback((value:ToolsTab)=>{setVisited(previous=>previous.includes(value)?previous:[...previous,value]);setTab(value);},[]);
 useEffect(()=>open(initialTab),[initialTab,open]);
 return <PanelEnvironment.Provider value={environment}><section className="trading-tools-panel" aria-label={environment==='live'?'LIVE 交易計畫與提醒':'交易計畫與提醒'} style={{minWidth:0,overflowWrap:'anywhere'}}>
  <div className="tabs" role="tablist" aria-label="交易工具">{([['plans','交易計畫'],['alerts','條件提醒'],['broker','券商紀錄']] as const).map(([value,label])=><button key={value} id={`${id}-${value}`} type="button" role="tab" aria-selected={tab===value} aria-controls={`${id}-content`} className={tab===value?'active':''} onClick={()=>open(value)}>{label}</button>)}</div>
  <div id={`${id}-content`} role="tabpanel" aria-labelledby={`${id}-${tab}`}>
   {visited.includes('plans')&&<div hidden={tab!=='plans'}><PanelActivity.Provider value={active&&tab==='plans'}><PlansPanel light={light} onOpenThread={onOpenThread}/></PanelActivity.Provider></div>}
   {visited.includes('alerts')&&<div hidden={tab!=='alerts'}><PanelActivity.Provider value={active&&tab==='alerts'}><AlertsPanel market={market} conversationId={conversationId} onOpenThread={onOpenThread}/></PanelActivity.Provider></div>}
   {active&&tab==='broker'&&<BrokerAccountPanel market={market} environment={environment} initialTab="history" idPrefix={environment==='live'?'live-records-':'tools-history-'}/>}
  </div>
 </section></PanelEnvironment.Provider>;
}

