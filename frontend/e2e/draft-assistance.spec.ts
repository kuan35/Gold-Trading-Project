import {test,expect,type Page} from '@playwright/test';
const at='2000-01-01T00:00:00Z',sid='c'.repeat(64);
const program={analysis_ref:'a'.repeat(64),provider:'local_market_rules',model:null,llm_status:'not_requested',market_status:'FROZEN',as_of_utc:at,quote_time_utc:at,snapshot_id:sid,analysis_mode:'draft_snapshot',source:'synthetic',message:'合成程式檢查',draft:null,followups:[],evidence:[],sections:[{title:'程式檢查',text:'合成程式檢查保留',fact_ids:['f5.trend']}]};
const agent={...program,analysis_ref:'b'.repeat(64),provider:'claude_market_analysis',model:'sonnet',llm_status:'ok',sections:[
 {title:'助手解讀',text:'合成助手依原草稿說明風險，不代為確認。',fact_ids:['draft.risk'],source:'model'},
 {title:'案例細節',text:'合成逐案明細',fact_ids:['history.case1'],source:'model'},
]};
const directionAdvice={...program,analysis_ref:'d'.repeat(64),market_status:'CURRENT',analysis_mode:'live',trade_advice:{
 action:'WAIT',side:null,headline:'建議等待',reason:'目前盤面尚未確認。',
 signal:'區間內',as_of:946684800,
 simulations:{count:0,BUY:{median_pct:null,positive:0,better:0,stress_median_pct:null},SELL:{median_pct:null,positive:0,better:0,stress_median_pct:null}},
 original:{BUY:{count:0,median_pct:null,positive:0,negative:0},SELL:{count:0,median_pct:null,positive:0,negative:0}},costs:null,draft:null,
}};
const orderTurn=(page:Page)=>page.locator('.ag-turn').filter({has:page.getByText('檢查目前委託',{exact:true})});
async function setup(page:Page,{failure,statusReady=true,submissionStatus,cancelFailure=false,expired=false,refreshFailure=false,expiryRace=false}:{failure?:'http'|'fallback';statusReady?:boolean;submissionStatus?:string;cancelFailure?:boolean;expired?:boolean;refreshFailure?:boolean;expiryRace?:boolean}={}){
 let drafts=0,confirmed=false;
 let release!:()=>void;const gate=new Promise<void>(r=>release=r),posts:{path:string;body:any}[]=[];
 await page.addInitScript(()=>localStorage.setItem('gold-desk-claude-selection-v1',JSON.stringify({provider:'claude_code',model:'sonnet',effort:'high'})));
 await page.route('**/api/**',async r=>{
  const path=new URL(r.request().url()).pathname;const json=(v:unknown)=>r.fulfill({json:v});
  if(path.startsWith('/api/assistant/analyses/'))return json(path.endsWith(directionAdvice.analysis_ref)?directionAdvice:path.endsWith(agent.analysis_ref)?agent:program);
  if(path==='/api/assistant/snapshots/'+sid+'/charts'){
   const bars=Array.from({length:60},(_,i)=>({time:946660000+i*300,open:4000+i,high:4002+i,low:3999+i,close:4001+i,volume:50}));
   return json({snapshot_id:sid,query:{'5m':bars,'1h':bars.slice(-20)},cases:[],analysis:{as_of_utc:at,frames:{'5m':{bars,layers:[]},'1h':{bars:bars.slice(-20),layers:[]}}}});
  }
  if(path==='/api/assistant/status')return json({configured:statusReady,enabled:statusReady,provider:'claude_code',model:'sonnet',supports_vision:false});
  if(path==='/api/broker/market')return json({environment:'demo',connection_status:'CONNECTED',token_scope:'TRADE',order_connection:true,symbol:{lot_size_cents:10000,min_volume_cents:100,max_volume_cents:100000,step_volume_cents:100,digits:2},quote:{status:'CURRENT',bid:'4000',ask:'4000.20',age_seconds:0,source_time_utc:at},account:{status:'CURRENT',currency:'USD',balance:'10000',equity:'10000',positions:[],pending_orders:[],all_positions_count:0,all_pending_orders_count:0,updated_at_utc:confirmed?'2000-01-01T00:00:02Z':at}});
  if(r.request().method()==='POST'){
   const body=r.request().postDataJSON();posts.push({path,body});
   if(path==='/api/assistant/interpret')return json({intent:'DISCUSS',analysis_side:'BUY',patch:{},proposal:{},message:'合成討論',input_revision:body.input_revision});
   if(path==='/api/assistant/live-chat')return json(body.advice_mode==='COMPARE'?directionAdvice:{...program,market_status:'CURRENT',analysis_mode:'live'});
   if(path==='/api/broker/ticket-preview'){
    const level=(price:string)=>price?{status:'AVAILABLE',reason:null,pnl_usd:((Number(price)-4000)*Number(body.lot)*100).toFixed(2),price_return_pct:((Number(price)-4000)/4000*100).toFixed(4),margin_roi_pct:((Number(price)-4000)/4000*100*200).toFixed(4)}:null;
    return json({status:'AVAILABLE',reason:null,entry_price:'4000',quantity_oz:'50',sl:level(body.sl),tp:level(body.tp),margin:{source:'LEVERAGE_ESTIMATE',amount_usd:'1000.00',leverage:'200',reason:'合成槓桿假設'},account_zero:{status:'AVAILABLE',reason:null,zero_bid_price:'3800.20',direction:'DOWN',conditional_on_fill:true,basis:'固定部位與價差，忽略停損及強平'},basis:'未扣交易成本',quote_time_utc:at});
   }
   if(path==='/api/broker/drafts'){
    drafts++;if(refreshFailure&&drafts>1)return r.fulfill({status:503,json:{detail:'合成最新報價尚未就緒'}});
    return json({id:drafts===1?'synthetic-draft':'synthetic-draft-'+drafts,revision:1,side:'BUY',lot:'0.5',order_type:'LIMIT',price:'4000',sl:'3990',tp:'4020',expires_at_utc:new Date(Date.now()+(expired&&drafts===1?-1000:30000)).toISOString(),risk:{before_lot:drafts===1?'0':'0.1',after_lot:drafts===1?'0.5':'0.6',stop_loss_usd:'500',scenarios:[],warnings:[]},analysis_reply:program,analysis_snapshot_id:sid,analysis_as_of_utc:at});
   }
   if(path.endsWith('/confirm')&&submissionStatus){if(expiryRace&&path==='/api/broker/drafts/synthetic-draft/confirm')return r.fulfill({status:409,json:{detail:'DEMO 草稿已超過 30 秒，請重新檢查'}});confirmed=true;return json({status:submissionStatus,order_id:'synthetic-order',status_observed_at_utc:at});}
   if(path==='/api/assistant/draft-chat'){await gate;try{return failure==='http'?await r.fulfill({status:503,json:{detail:'合成模型失敗'}}):await json(failure==='fallback'?{...program,llm_status:'invalid_grounding'}:{...agent,trade_advice:directionAdvice.trade_advice});}catch{return;}}
   if(path.endsWith('/cancel'))return cancelFailure?r.fulfill({status:503,json:{detail:'合成取消失敗'}}):json({status:'CANCELLED'});
   return r.fulfill({status:403,json:{detail:'All other mutations blocked'}});
  }
  if(path.endsWith('/status')&&path.includes('/broker/drafts/'))return json({status:submissionStatus??'UNKNOWN',status_observed_at_utc:at});
  if(path==='/api/broker/chart-stream')return r.abort();return r.continue();
 });
 await page.goto('/');await expect(page.locator('.ag-center')).toBeVisible();
 const panel=page.locator('#ag-order-panel');await panel.getByRole('button',{name:'做多 BUY',exact:true}).click();await expect(page.locator('.ag-thinking')).toHaveCount(0);
 await panel.getByRole('button',{name:'限價',exact:true}).click();await panel.locator('#side-ticket-lot').fill('0.5');await panel.locator('#side-ticket-limit').fill('4000');await panel.locator('#side-ticket-sl').fill('3990');await panel.locator('#side-ticket-tp').fill('4020');
 return {panel,posts,release};
}
test('zero-equity scenario is visible before checking even without stop-loss or take-profit',async({page})=>{
 const {panel,posts}=await setup(page);await panel.locator('#side-ticket-sl').fill('');await panel.locator('#side-ticket-tp').fill('');
 await expect(panel.getByRole('region',{name:'帳戶淨值歸零情境'})).toContainText('跌至 3800.20');
 await expect(panel.getByRole('region',{name:'帳戶淨值歸零情境'})).toContainText('不是強平價');
 expect(posts.some(p=>p.path==='/api/broker/drafts')).toBe(false);
});
test('expired checked order keeps its inputs and can refresh then confirm without another model call',async({page})=>{
 const {panel,posts,release}=await setup(page,{expired:true,submissionStatus:'ACCEPTED'});release();
 await panel.getByRole('button',{name:'檢查 DEMO 委託',exact:true}).click();
 await expect.poll(()=>posts.some(p=>p.path==='/api/assistant/draft-chat')).toBe(true);
 const refresh=page.getByRole('button',{name:'更新報價並繼續',exact:true});await expect(refresh).toBeEnabled();await refresh.click();
 await expect(page.getByRole('region',{name:'委託更新對照'})).toContainText('0.5 → 0.6');
 await expect(panel.locator('#side-ticket-lot')).toHaveValue('0.5');
 expect(posts.filter(p=>p.path==='/api/broker/drafts')).toHaveLength(2);
 expect(posts.filter(p=>p.path==='/api/assistant/draft-chat')).toHaveLength(1);
 expect(posts.some(p=>p.path.endsWith('/confirm'))).toBe(false);
 await page.getByRole('button',{name:'確認送出 DEMO 委託',exact:true}).click();
 expect(posts.filter(p=>p.path.endsWith('/confirm'))[0].path).toContain('synthetic-draft-2');
});
test('server expiry between click and confirmation is refreshable instead of an unknown receipt',async({page})=>{
 const {panel,posts,release}=await setup(page,{expiryRace:true,submissionStatus:'ACCEPTED'});release();
 await panel.getByRole('button',{name:'檢查 DEMO 委託',exact:true}).click();
 await page.getByRole('button',{name:'確認送出 DEMO 委託',exact:true}).click();
 await expect(page.getByRole('button',{name:'更新報價並繼續',exact:true})).toBeEnabled();
 await page.getByRole('button',{name:'更新報價並繼續',exact:true}).click();
 await page.getByRole('button',{name:'確認送出 DEMO 委託',exact:true}).click();
 expect(posts.filter(p=>p.path.endsWith('/confirm')).map(p=>p.path)).toEqual(['/api/broker/drafts/synthetic-draft/confirm','/api/broker/drafts/synthetic-draft-2/confirm']);
});
test('refresh without a current quote preserves the expired review and offers retry',async({page})=>{
 const {panel,posts,release}=await setup(page,{expired:true,refreshFailure:true});release();
 await panel.getByRole('button',{name:'檢查 DEMO 委託',exact:true}).click();
 await page.getByRole('button',{name:'更新報價並繼續',exact:true}).click();
 await expect(panel.getByRole('alert')).toContainText('合成最新報價尚未就緒');
 await expect(panel.locator('#side-ticket-lot')).toHaveValue('0.5');
 await expect(page.getByRole('button',{name:'更新報價並繼續',exact:true})).toBeEnabled();
 expect(posts.some(p=>p.path.endsWith('/confirm')||p.path.endsWith('/cancel'))).toBe(false);
});
test('draft direction only fills fields; cancel preparation clears both tickets without sending an order',async({page})=>{
 const {panel,posts}=await setup(page);
 expect(posts.some(p=>p.path==='/api/assistant/live-chat')).toBe(false);
 await panel.getByRole('button',{name:'取消準備中委託',exact:true}).click();
 await expect(panel.locator('#side-ticket-lot')).toHaveValue('');
 await expect(panel.locator('#side-ticket-sl')).toHaveValue('');
 await expect(panel.locator('#side-ticket-tp')).toHaveValue('');
 await expect(panel).toContainText('尚未選擇方向');
 await page.locator('.cw-inline > summary').click();
 await expect(page.locator('#chat-ticket-lot')).toHaveValue('');
 expect(posts.some(p=>p.path==='/api/broker/drafts'||p.path.endsWith('/confirm'))).toBe(false);
});
test('cancel preparation cancels the checked draft and rejects a late agent answer',async({page})=>{
 const {panel,posts,release}=await setup(page);
 await panel.getByRole('button',{name:'檢查 DEMO 委託',exact:true}).click();
 await expect.poll(()=>posts.some(p=>p.path==='/api/assistant/draft-chat')).toBe(true);
 await panel.getByRole('button',{name:'取消準備中委託',exact:true}).click();release();
 await expect(page.getByRole('button',{name:'確認送出 DEMO 委託',exact:true})).toHaveCount(0);
 await expect(panel.locator('#side-ticket-lot')).toHaveValue('');
 expect(posts.filter(p=>p.path.endsWith('/cancel'))).toHaveLength(1);
 expect(posts.some(p=>p.path.endsWith('/confirm'))).toBe(false);
 await expect(page.locator('.ag-log')).not.toContainText('合成助手依原草稿');
});
test('failed cancellation preserves the checked draft and fields',async({page})=>{
 const {panel,release}=await setup(page,{cancelFailure:true});release();
 await panel.getByRole('button',{name:'檢查 DEMO 委託',exact:true}).click();
 await expect(page.getByRole('button',{name:'確認送出 DEMO 委託',exact:true})).toBeVisible();
 await panel.getByRole('button',{name:'取消準備中委託',exact:true}).click();
 await expect(panel.getByRole('alert')).toContainText('合成取消失敗');
 await expect(panel.locator('#side-ticket-lot')).toHaveValue('0.5');
 await expect(page.getByRole('button',{name:'確認送出 DEMO 委託',exact:true})).toBeVisible();
});
test('instant preview and order review remain available while chat waits for the selected agent',async({page})=>{
 const {panel,posts,release}=await setup(page,{statusReady:false});
 await expect(panel.locator('.ticket-level').first()).toContainText('-500.00 USD');await expect(panel.locator('.ticket-level').last()).toContainText('+1000.00 USD');
 await expect(panel.locator('.ticket-level').first()).toContainText('-0.2500%');expect(posts.some(p=>p.path==='/api/broker/drafts')).toBe(false);
 await expect(panel.locator('.ticket-level').first()).toContainText('預估保證金報酬率 -50.0000%');
 await expect(panel.locator('.ticket-level').last()).toContainText('預估保證金報酬率 +100.0000%');
 await expect(panel).toContainText('1000.00 USD · 1:200 試算');
 await panel.getByRole('button',{name:'檢查 DEMO 委託',exact:true}).click();
 await expect(page.getByRole('button',{name:'確認送出 DEMO 委託',exact:true})).toBeVisible();
 await expect(page.getByText('助手正在解讀這份固定草稿快照…',{exact:true})).toBeVisible();
 await expect(orderTurn(page)).not.toContainText(/程式解讀|合成程式檢查|建議等待/);
 await expect.poll(()=>posts.some(p=>p.path==='/api/assistant/draft-chat')).toBe(true);
 const sent=posts.find(p=>p.path==='/api/assistant/draft-chat')!.body;expect(sent.draft_id).toBe('synthetic-draft');expect(sent.provider).toBe('claude_code');expect(sent.effort).toBe('high');
 release();await expect(page.locator('.ag-log')).toContainText('合成助手依原草稿');
 await expect(orderTurn(page).getByText('合成逐案明細',{exact:true})).toHaveCount(0);
 await expect(orderTurn(page).getByRole('region',{name:'下單前建議'})).toHaveCount(0);
 await orderTurn(page).getByRole('button',{name:/展開完整分析與案例/}).click();
 await expect(orderTurn(page).getByRole('region',{name:'下單前建議'})).toBeVisible();
 await expect(orderTurn(page).getByText('合成逐案明細',{exact:true})).toBeVisible();
 await orderTurn(page).getByText('什麼是一組完整配對？',{exact:true}).click();
 await expect(orderTurn(page).getByText(/它要有完整的後續 30 分鐘/)).toBeVisible();
 expect(posts.some(p=>p.path.endsWith('/confirm'))).toBe(false);
});

for(const status of ['ACCEPTED','FILLED','UNKNOWN'])test(`next order after ${status} respects receipt and account synchronization`,async({page})=>{
 const {panel,posts,release}=await setup(page,{submissionStatus:status});release();
 await panel.getByRole('button',{name:'檢查 DEMO 委託',exact:true}).click();
 await page.getByRole('button',{name:'確認送出 DEMO 委託',exact:true}).click();
 await expect(panel.getByRole('button',{name:'取消準備中委託',exact:true})).toBeDisabled();
 const next=page.getByRole('button',{name:'準備下一筆委託',exact:true});
 if(status==='UNKNOWN'){
  await expect(next).toBeDisabled();await expect(panel.locator('#side-ticket-lot')).toBeDisabled();
  expect(posts.filter(p=>p.path==='/api/broker/drafts')).toHaveLength(1);return;
 }
 await expect(next).toBeEnabled({timeout:12000});await next.click();
 await expect(panel.locator('#side-ticket-lot')).toBeEnabled();
 await panel.getByRole('button',{name:'檢查 DEMO 委託',exact:true}).click();
 await expect.poll(()=>posts.filter(p=>p.path==='/api/broker/drafts').length).toBe(2);
 expect(posts.filter(p=>p.path.endsWith('/confirm'))).toHaveLength(1);
 expect(posts.filter(p=>p.path.endsWith('/cancel'))).toHaveLength(0);
 await expect(page.getByRole('button',{name:'確認送出 DEMO 委託',exact:true})).toBeVisible();
});
test('editing checked fields cancels display of an old agent answer',async({page})=>{
 const {panel,posts,release}=await setup(page);await panel.getByRole('button',{name:'檢查 DEMO 委託',exact:true}).click();
 await expect.poll(()=>posts.some(p=>p.path==='/api/assistant/draft-chat')).toBe(true);
 await panel.locator('#side-ticket-sl').fill('3980');release();
 await expect(page.getByRole('button',{name:'確認送出 DEMO 委託',exact:true})).toHaveCount(0);
 await expect(panel.locator('.ticket-level').first()).toContainText('-1000.00 USD');await expect(page.locator('.ag-log')).not.toContainText('合成助手依原草稿');await expect(page.locator('.ag-log')).toContainText('這次助手分析已取消');
});
for(const failure of ['http','fallback'] as const)test(`agent ${failure} shows an error without posting a program answer`,async({page})=>{
 const {panel,posts,release}=await setup(page,{failure});await panel.getByRole('button',{name:'檢查 DEMO 委託',exact:true}).click();
 await expect.poll(()=>posts.some(p=>p.path==='/api/assistant/draft-chat')).toBe(true);release();
 await expect(page.locator('.ag-log')).toContainText('助手未能完成這次委託分析');
 await expect(orderTurn(page)).not.toContainText(/程式解讀|合成程式檢查/);
 await expect(page.getByRole('button',{name:'確認送出 DEMO 委託',exact:true})).toBeVisible();expect(posts.some(p=>p.path.endsWith('/confirm'))).toBe(false);
});
test('only the agent response can open draft charts and it survives reload',async({page})=>{
 const {panel,posts,release}=await setup(page);await panel.getByRole('button',{name:'檢查 DEMO 委託',exact:true}).click();
 await expect.poll(()=>posts.some(p=>p.path==='/api/assistant/draft-chat')).toBe(true);
 await expect(orderTurn(page).getByRole('button',{name:'看圖',exact:true})).toHaveCount(0);release();
 await expect(page.locator('.ag-log')).toContainText('合成助手依原草稿');
 await orderTurn(page).getByRole('button',{name:'看圖',exact:true}).click();
 await expect(page.locator('.ag-chart-evidence canvas').first()).toBeVisible();
 await page.reload();await expect(page.locator('.ag-chart-evidence canvas').first()).toBeVisible();await expect(page.locator('.ag-log')).toContainText('合成助手依原草稿');
});
test('the original historical trade is shown with the agent plan without expanding the statistics',async({page})=>{
 const {panel}=await setup(page);
 await page.route('**/api/assistant/draft-chat',r=>r.fulfill({json:{...agent,trade_advice:{...directionAdvice.trade_advice,simulations:{...directionAdvice.trade_advice.simulations,count:1}},sections:[agent.sections[0],
  {title:'歷史操作參照',text:'2023年10月03日交易員做多，1780進場、1789平倉，原單價格報酬0.5056%。',source:'model',fact_ids:['history.trade1','history.case1']},
  {title:'完整統計',text:'隱藏的樣本詳細資訊',source:'model',fact_ids:['advice.comparison']} ]}}));
 await panel.getByRole('button',{name:'檢查 DEMO 委託',exact:true}).click();
 await expect(orderTurn(page)).toContainText('2023年10月03日');
 await expect(orderTurn(page)).toContainText('0.5056%');
 await expect(orderTurn(page).getByLabel('本次建議的案例數')).toContainText('多空試算參考 1 組');
 await expect(orderTurn(page).getByText('隱藏的樣本詳細資訊',{exact:true})).toHaveCount(0);
});

test('mobile order overlay has an opaque background instead of blending chat text through fields',async({page})=>{
 await page.setViewportSize({width:390,height:844});const {panel,release}=await setup(page);release();
 await expect(panel).toBeVisible();
 const background=await page.locator('.ag-drawer').evaluate(e=>getComputedStyle(e).backgroundColor);
 expect(background).not.toMatch(/rgba\([^)]*,\s*0\./);
});

test('the complete matching pool is averaged and selecting each historical chart shows its ledger times',async({page})=>{
 const {panel}=await setup(page);
 const cases=['案例甲','案例乙'].map(ref=>({ref,event:'區間內',tail_direction:'上行',similarities:[],differences:[],metrics:[]}));
 const performance={status:'AVAILABLE',total:6,known_results:6,wins:3,losses:2,flat:1,unknown_results:0,win_rate_pct:'50.00',
  price_results_count:6,mean_price_return_pct:'16.6667',mean_move_per_oz:'16.6667',unknown_currency_results:0,
  pnl_by_currency:[{currency:'USD',count:6,mean_pnl:'16.67',mean_win:'43.33',mean_loss:'-15.00'}]};
 await page.route('**/api/assistant/draft-chat',r=>r.fulfill({json:{...agent,case_comparison:{status:'PASSED',side:'BUY',
  label:'符合案例',reason:'synthetic',counts:{eligible:12,passed:6,displayed:2},query_state:{event:'區間內',tail_direction:'上行'},
  rejections:[],cases,performance},sections:[agent.sections[0]]}}));
 await page.route('**/api/assistant/snapshots/'+sid+'/charts',r=>{
  const bars=Array.from({length:60},(_,i)=>({time:946660200+i*300,open:4000+i,high:4002+i,low:3999+i,close:4001+i}));
  return r.fulfill({json:{snapshot_id:sid,query_as_of_utc:946684800,query:{'5m':bars,'1h':bars.slice(-20)},cases:cases.map((c,i)=>({
   ref:c.ref,as_of_utc:946684800,'5m':bars,'1h':bars.slice(-20),
   original_times:{opened_at:`2023-10-0${i+3} 08:00:00`,closed_at:`2023-10-0${i+3} 09:00:00`}})),
   analysis:{frames:{'5m':{bars,layers:[]},'1h':{bars:bars.slice(-20),layers:[]}}}}});
 });
 await panel.getByRole('button',{name:'檢查 DEMO 委託',exact:true}).click();
 const summary=page.getByRole('region',{name:'歷史相似案例整體表現'});
 await expect(summary).toContainText('全部 6 組');await expect(summary).toContainText('50.00%');await expect(summary).toContainText('16.6667%');
 await expect(summary).toContainText('16.67 USD');
 await orderTurn(page).getByRole('button',{name:'查看 K 線證據',exact:true}).click();
 await expect(page.locator('.case-fused-comparison')).toContainText('2023-10-03 08:00:00');
 await page.getByRole('combobox',{name:'歷史案例',exact:true}).selectOption('案例乙');
 await expect(page.locator('.case-fused-comparison')).toContainText('2023-10-04 08:00:00');
 await expect(page.locator('.case-fused-comparison')).not.toContainText('2023-10-03 08:00:00');
});

test('compare advice keeps the draft, carries the shared budget and can be reopened after reload',async({page})=>{
 const {panel,posts,release}=await setup(page);release();
 await panel.getByText('依可承擔風險反算手數',{exact:true}).click();
 await panel.locator('#side-ticket-risk-budget').fill('35');
 const interpretations=posts.filter(p=>p.path==='/api/assistant/interpret').length;
 await page.getByRole('button',{name:'現在該做多還是做空？',exact:true}).click();
 const advice=page.getByRole('region',{name:'下單前建議'});
 await expect(advice).toContainText('建議等待');
 expect(posts.filter(p=>p.path==='/api/assistant/interpret')).toHaveLength(interpretations);
 expect(posts.find(p=>p.body.advice_mode==='COMPARE')?.body.draft).toMatchObject({side:'BUY',lot:'0.5',risk_usd:'35'});
 await expect(panel.locator('#side-ticket-lot')).toHaveValue('0.5');
 await panel.getByRole('button',{name:'檢查 DEMO 委託',exact:true}).click();
 await expect.poll(()=>posts.find(p=>p.path==='/api/broker/drafts')?.body.risk_usd).toBe('35');
 expect(posts.some(p=>p.path.endsWith('/confirm'))).toBe(false);
 await page.reload();
 await expect(advice).toContainText('建議等待');
});


test('same frozen agent explanation appears in chat and confirmation without a competing program verdict',async({page})=>{
 const {panel,release}=await setup(page);await panel.getByRole('button',{name:'檢查 DEMO 委託',exact:true}).click();
 const review=page.getByRole('region',{name:'這筆委託的助手評估'});
 await expect(review).toContainText('助手正在評估這筆委託');await expect(review).not.toContainText('建議等待');
 release();await expect(review).toContainText(agent.sections[0].text);
 await expect(orderTurn(page)).toContainText(agent.sections[0].text);await expect(review).not.toContainText('建議等待');
});

test('an HTML 500 on draft creation keeps fields and identifies the server failure',async({page})=>{
 const {panel}=await setup(page);
 await page.route('**/api/broker/drafts',r=>r.fulfill({status:500,contentType:'text/html',body:'<html>Internal Server Error</html>'}));
 await panel.getByRole('button',{name:'檢查 DEMO 委託',exact:true}).click();
 await expect(panel.getByRole('alert')).toContainText('HTTP 500');
 await expect(panel.getByRole('alert')).not.toContainText('後端已啟動');
 await expect(panel.locator('#side-ticket-lot')).toHaveValue('0.5');await expect(panel.locator('#side-ticket-limit')).toHaveValue('4000');
});

test('slow previews survive successive quote timestamps and retain panel geometry while updating',async({page})=>{
 const {panel}=await setup(page);let n=0,completed=0,active=0,maxActive=0;
 await page.route('**/api/broker/market',r=>r.fulfill({json:{environment:'demo',connection_status:'CONNECTED',token_scope:'TRADE',order_connection:true,symbol:{lot_size_cents:10000,min_volume_cents:100,max_volume_cents:100000,step_volume_cents:100,digits:2},quote:{status:'CURRENT',bid:'4000',ask:'4000.20',age_seconds:0,source_time_utc:new Date(Date.now()+n++).toISOString()},account:{status:'CURRENT',currency:'USD',equity:'10000',positions:[],pending_orders:[],all_positions_count:0,all_pending_orders_count:0,updated_at_utc:at}}}));
 await page.route('**/api/broker/ticket-preview',async r=>{active++;maxActive=Math.max(maxActive,active);await new Promise(resolve=>setTimeout(resolve,2400));try{await r.fulfill({json:{status:'AVAILABLE',entry_price:'4000',quantity_oz:'50',sl:null,tp:null,margin:{source:'LEVERAGE_ESTIMATE',amount_usd:'1000.00',leverage:'200'},account_zero:{status:'AVAILABLE',zero_bid_price:'3800.20',direction:'DOWN',conditional_on_fill:true,basis:'合成情境'},quote_time_utc:at}});completed++;}finally{active--;}});
 await panel.locator('#side-ticket-lot').fill('0.4');
 await expect.poll(()=>completed,{timeout:12000}).toBeGreaterThan(0);
 const details=panel.locator('.account-zero-estimate details');await details.locator('summary').click();
 await expect(details).toHaveAttribute('open','');
 const measure=()=>panel.getByRole('button',{name:'檢查 DEMO 委託',exact:true}).evaluate(e=>e.getBoundingClientRect().top);
 const before=await measure();await expect(panel).toContainText('上次試算 · 更新中',{timeout:6000});
 expect(Math.abs((await measure())-before)).toBeLessThan(2);
 await expect.poll(()=>completed,{timeout:10000}).toBeGreaterThan(1);
 expect(Math.abs((await measure())-before)).toBeLessThan(2);expect(maxActive).toBe(1);
 await expect(details).toHaveAttribute('open','');
});

test('switching chats cancels the checked-order assessment state instead of leaving an endless pending review',async({page})=>{
 const {panel,posts,release}=await setup(page);await panel.getByRole('button',{name:'檢查 DEMO 委託',exact:true}).click();
 await expect.poll(()=>posts.some(p=>p.path==='/api/assistant/draft-chat')).toBe(true);
 await page.getByRole('button',{name:'新對話',exact:true}).click();
 await expect(page.getByRole('region',{name:'這筆委託的助手評估'})).toContainText('這次助手分析已取消');
 await expect(page.getByRole('region',{name:'這筆委託的助手評估'})).not.toContainText('正在評估');
 release();await expect(page.getByRole('region',{name:'這筆委託的助手評估'})).not.toContainText(agent.sections[0].text);
});
