import test from 'node:test';
import assert from 'node:assert/strict';
import {createElement} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {readFileSync} from 'node:fs';

const modulePath = '../src/TradingToolsPanel.tsx';
const load = async () => import(modulePath);
const market = {source:'ctrader_demo_xauusd',environment:'demo',connection_status:'CONNECTED',
 quote:{status:'CURRENT',bid:'2500.30',ask:'2500.50',age_seconds:1},account:{status:'CURRENT'}};

test('alert readiness rejects old, disconnected and different-source quotes',async()=>{
 const {alertAvailability}=await load();
 assert.equal(alertAvailability(market), '');
 for(const value of [null,{...market,source:'synthetic_demo'}, {...market,connection_status:'DISCONNECTED'},
  {...market,quote:{...market.quote,status:'STALE'}},{...market,quote:{...market.quote,age_seconds:6}},
  {...market,account:{status:'STALE'}}]) assert.notEqual(alertAvailability(value),'');
});

test('alert requests preserve decimal text and never trust browser event times',async()=>{
 const {alertRequest}=await load();
 assert.deepEqual(alertRequest({name:'價位',kind:'PRICE',field:'ask',comparator:'GTE',threshold:'2500.3000'},'thread'),
  {name:'價位',kind:'PRICE',field:'ask',comparator:'GTE',threshold:'2500.3000',conversation_id:'thread'});
 assert.equal(alertRequest({name:'收盤',kind:'CLOSE_5M',field:'ask',comparator:'LTE',threshold:'2500'}).field,'bid');
 assert.deepEqual(alertRequest({name:'官方事件',kind:'EVENT',event_id:'event-1',lead_minutes:'15',time_utc:'untrusted'}),
  {name:'官方事件',kind:'EVENT',event_id:'event-1',lead_minutes:15});
});

test('saved plan evidence keeps original text separate from review and fixes chart height',async()=>{
 const {PlanEvidence,planQueryBars}=await load();
 const bar={time:100,open:1,high:2,low:1,close:2};
 const plan={id:'p',draft_id:'d',revision:2,created_at_utc:'2026-11-04T01:00:00Z',note:'原理由 <script>',
  review_note:'事後看法',adherence:'UNKNOWN',lesson:'',draft:{side:'BUY',lot:'0.10',price:'2500.300'},
  analysis:{snapshot_id:'fixed',as_of_utc:'2026-11-03T01:00:00Z',sections:[{title:'支持',text:'固定盤面'}],case_comparison:{status:'NO_RULE_MATCH',reason:'沒有符合案例'}},
  charts:{snapshot_id:'fixed',query:{'5m':[bar],'1h':[bar]}}};
 const html=renderToStaticMarkup(createElement(PlanEvidence,{plan,light:false}));
 assert.match(html,/原理由 &lt;script&gt;/);assert.doesNotMatch(html,/<script>/);
 assert.match(html,/固定盤面/);assert.match(html,/沒有符合案例/);
 assert.match(html,/2026-11-03/);assert.equal((html.match(/height:280px;max-height:280px/g)??[]).length,2);
 assert.deepEqual(planQueryBars(plan,'5m'),[bar]);
 assert.deepEqual(planQueryBars({...plan,charts:{...plan.charts,snapshot_id:'different'}},'5m'),[]);
});

test('latest-request guard ignores replies arriving after selection changes or cancellation',async()=>{
 const {LatestTradingRequest}=await load();
 const request=new LatestTradingRequest();const seen:string[]=[];
 let finishOld!:(value:string)=>void,finishNew!:(value:string)=>void;
 const old=request.run(()=>new Promise<string>(r=>{finishOld=r;}),v=>seen.push(v));
 const latest=request.run(()=>new Promise<string>(r=>{finishNew=r;}),v=>seen.push(v));
 finishNew('new-plan');await latest;finishOld('old-plan');await old;
 assert.deepEqual(seen,['new-plan']);
 let finish!:(value:string)=>void;
 const pending=request.run(()=>new Promise<string>(r=>{finish=r;}),v=>seen.push(v));
 request.cancel();finish('hidden/unmounted');await pending;
 assert.deepEqual(seen,['new-plan']);
});

test('HTTP helpers preserve conflict status and use only the trading endpoint',async()=>{
 const {tradingRequest,TradingRequestError}=await load();
 const calls:any[]=[];
 const fetcher=async(...args:any[])=>{calls.push(args);return new Response(JSON.stringify({detail:'版本已變'}),{status:409});};
 await assert.rejects(tradingRequest('/plans/p/review',{method:'PATCH',body:{revision:1,note:'復盤'}},fetcher),
  (error:any)=>error instanceof TradingRequestError&&error.status===409);
 assert.equal(calls[0][0],'/api/trading/plans/p/review');assert.equal(calls[0][1].method,'PATCH');
 assert.deepEqual(JSON.parse(calls[0][1].body),{revision:1,note:'復盤'});
});

test('hidden polling aborts work and resumes once without accepting its late result',async()=>{
 const {startTradingPolling}=await load();
 let listener=()=>{};const tasks:Array<()=>void>=[],seen:string[]=[];
 const page={hidden:false,addEventListener:(_name:string,callback:()=>void)=>{listener=callback;},removeEventListener:()=>{listener=()=>{};}};
 const pending:Array<{resolve:(value:string)=>void;signal:AbortSignal}>=[];
 const stop=startTradingPolling((signal:AbortSignal)=>new Promise<string>(resolve=>pending.push({signal,resolve})),(value:string)=>seen.push(value),()=>{},
  {page,setTimer:(task:()=>void)=>{tasks.push(task);return tasks.length;},clearTimer:(id:number)=>{tasks[id-1]=()=>{};}});
 assert.equal(pending.length,1);page.hidden=true;listener();assert.equal(pending[0].signal.aborted,true);
 page.hidden=false;listener();assert.equal(pending.length,2);
 pending[0].resolve('old');pending[1].resolve('new');await new Promise(resolve=>setImmediate(resolve));
 assert.deepEqual(seen,['new']);assert.equal(tasks.length,1);
 stop();tasks[0]();assert.equal(pending.length,2);
});

test('retained inactive tools do no polling and resume only once when activated',async()=>{
 const {startTradingPolling}=await load();
 let reads=0;const page={hidden:false,addEventListener:()=>{},removeEventListener:()=>{}};
 const tasks:Array<()=>void>=[];
 const environment={page,setTimer:(task:()=>void)=>{tasks.push(task);return tasks.length;},clearTimer:(id:number)=>{tasks[id-1]=()=>{};}};
 const read=async()=>{reads++;return 'read';};
 const inactive=startTradingPolling(read,()=>{},()=>{},environment,false);
 await new Promise(resolve=>setImmediate(resolve));assert.equal(reads,0);inactive();
 const active=startTradingPolling(read,()=>{},()=>{},environment,true);
 await new Promise(resolve=>setImmediate(resolve));assert.equal(reads,1);assert.equal(tasks.length,1);
 active();tasks[0]();assert.equal(reads,1);
});

test('explicit calendar refresh uses refresh=true and program reply never impersonates a model',async()=>{
 const {refreshTradingCalendar,planDiscussionLabel,default:TradingToolsPanel}=await load();
 const calls:string[]=[];const fetcher=async(url:string)=>{calls.push(url);return new Response(JSON.stringify({status:'AVAILABLE',events:[]}));};
 assert.equal(calls.length,0);await refreshTradingCalendar(undefined,fetcher);
 assert.deepEqual(calls,['/api/trading/calendar?refresh=true']);
 assert.equal(planDiscussionLabel({provider:'program',model:'configured-sonnet'}),'程式回顧');
 assert.match(planDiscussionLabel({provider:'claude_market_analysis',model:'sonnet'}),/sonnet/);
 const html=renderToStaticMarkup(createElement(TradingToolsPanel,{market:null,active:false,initialTab:'alerts'}));
 assert.match(html,/更新官方事件/);assert.match(html,/aria-selected="true"[^>]*>條件提醒/);
});

test('SSR renders three concise tools tabs and no eager model or transaction action',async()=>{
 const {default:TradingToolsPanel}=await load();
 const html=renderToStaticMarkup(createElement(TradingToolsPanel,{market:null}));
 for(const label of ['交易計畫','條件提醒','券商紀錄'])assert.match(html,new RegExp(label));
 assert.match(html,/檢查委託時/);assert.doesNotMatch(html,/送出交易|確認下單/);
 const source=readFileSync(new URL('../src/TradingToolsPanel.tsx',import.meta.url),'utf8');
 assert.match(source,/visibilitychange/);assert.match(source,/5000/);
 assert.match(source,/initialTab="history"/);
});

test('LIVE tools use only LIVE trading routes, LIVE readiness and LIVE risk sizing',async()=>{
 const {tradingRequest,refreshTradingCalendar,alertAvailability,tradingBase,default:TradingToolsPanel}=await load();
 const {riskSizePath}=await import('../src/TicketRiskPanel.tsx');
 const calls:string[]=[];const fetcher=async(url:string)=>{calls.push(url);return new Response(JSON.stringify({status:'AVAILABLE',events:[]}));};
 await tradingRequest('/plans?limit=20&offset=0',{environment:'live'},fetcher);
 await refreshTradingCalendar(undefined,fetcher,'live');
 assert.deepEqual(calls,['/api/live/trading/plans?limit=20&offset=0','/api/live/trading/calendar?refresh=true']);
 assert.equal(tradingBase(),'/api/trading');
 assert.equal(riskSizePath('live'),'/api/live/trading/risk-size');assert.equal(riskSizePath(),'/api/trading/risk-size');
 const live={...market,source:'ctrader_live_xauusd',environment:'live'};
 assert.equal(alertAvailability(live,'live'),'');
 assert.notEqual(alertAvailability(market,'live'),'');assert.notEqual(alertAvailability(live),'');
 const html=renderToStaticMarkup(createElement(TradingToolsPanel,{market:null,environment:'live'}));
 assert.match(html,/LIVE 交易計畫與提醒/);for(const label of ['交易計畫','條件提醒','券商紀錄'])assert.match(html,new RegExp(label));
 const workspace=readFileSync(new URL('../src/ConversationWorkspace.tsx',import.meta.url),'utf8');
 assert.match(workspace,/<TradingToolsPanel environment=\{environment\}/);
 assert.doesNotMatch(workspace,/environment==='demo'&&<details className="ticket-plan-note"/);
 const ticket=readFileSync(new URL('../src/SharedTicket.tsx',import.meta.url),'utf8');
 assert.match(ticket,/<TicketRiskPanel[^>]*environment=\{environment\}/);
});
