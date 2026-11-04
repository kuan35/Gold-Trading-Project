import {test,expect,type Page} from '@playwright/test';
const sid='e'.repeat(64),at='2026-01-01T00:00:00Z';
const bars=Array.from({length:80},(_,i)=>({time:1767200000+i*300,open:4000+Math.sin(i/8)*6,high:4009,low:3991,close:4000+Math.sin(i/8)*6,volume:30+i}));
const analysis={snapshot_id:sid,provider:'program',model:null,llm_status:'disabled',market_status:'FROZEN',source:'synthetic',as_of_utc:at,message:'固定依據',draft:null,followups:[],evidence:[],sections:[{title:'原始盤面',text:'當時為區間內反彈。',fact_ids:[]}],case_comparison:{status:'NO_RULE_MATCH',label:'無符合案例',reason:'試驗條件未通過',cases:[],rejections:[],counts:{eligible:10,passed:0,displayed:0}}};
async function setup(page:Page){
 const calls:{path:string;body:any;method:string}[]=[];
 let plan:any={id:'plan1',draft_id:'d1',created_at_utc:at,revision:1,note:'原始交易理由',review_note:'',adherence:'UNKNOWN',lesson:'',draft:{side:'BUY',lot:'0.1',price:'4000',sl:'3995',tp:'4005'},analysis,charts:{snapshot_id:sid,query:{'5m':bars.slice(-60),'1h':bars.slice(-20)}}};
 let alerts:any[]=[];let events:any[]=[];
 await page.addInitScript(({bars})=>{
  localStorage.setItem('gold-desk-claude-selection-v1',JSON.stringify({provider:'program'}));
  class ES{onmessage:any=null;onerror:any=null;constructor(url:string){setTimeout(()=>this.onmessage?.({data:JSON.stringify({interval:new URL(url,location.origin).searchParams.get('interval'),status:'CURRENT',source:'synthetic',bars,forming:null})}),40);}close(){}}
  (window as any).EventSource=ES;
 },{bars});
 await page.route('**/api/**',async r=>{
  const u=new URL(r.request().url()),p=u.pathname,m=r.request().method(),json=(value:any)=>r.fulfill({json:value});
  const body=m==='POST'||m==='PATCH'?r.request().postDataJSON():null;calls.push({path:p,body,method:m});
  const now=new Date().toISOString();
  if(p==='/api/broker/market')return json({source:'ctrader_demo_xauusd',environment:'demo',connection_status:'CONNECTED',token_scope:'TRADE',order_connection:true,symbol:{lot_size_cents:10000,min_volume_cents:100,step_volume_cents:100,max_volume_cents:100000,digits:2},quote:{status:'CURRENT',bid:'4000',ask:'4000.20',age_seconds:0,source_time_utc:now},account:{status:'CURRENT',pnl_status:'CURRENT',currency:'USD',equity:'10000',balance:'10000',net_unrealized_pnl:'0',xau_net_unrealized_pnl:'0',positions:[],pending_orders:[],updated_at_utc:now,pnl_updated_at_utc:now}});
  if(p==='/api/assistant/status')return json({provider:'program',configured:false,enabled:false});
  if(p==='/api/broker/bars')return json({status:'CURRENT',interval:u.searchParams.get('interval'),bars,forming:null});
  if(p==='/api/broker/ticket-preview')return json(body.lot?{status:'AVAILABLE',entry_price:'4000',quantity_oz:'10',sl:{status:'AVAILABLE',pnl_usd:'-50',price_return_pct:'-0.1250'},tp:{status:'AVAILABLE',pnl_usd:'50',price_return_pct:'0.1250'},basis:'合成測試',risk:{status:'AVAILABLE',reason:null,stop_equity_pct:'0.5000',reward_risk_ratio:'1.0000',gold_total_risk_usd:'50',gold_total_equity_pct:'0.5000',scope:'僅黃金名目風險'}}:{status:'UNAVAILABLE',reason:'請填手數'});
  if(p==='/api/trading/risk-size')return json({status:'AVAILABLE',lot:'0.1',actual_risk_usd:'50',budget_usd:'50'});
  if(p==='/api/broker/drafts')return json({id:'d1',revision:1,side:'BUY',lot:'0.1',order_type:'LIMIT',price:'4000',sl:'3995',tp:'4005',expires_at_utc:new Date(Date.now()+60000).toISOString(),risk:{before_lot:'0',after_lot:'0.1',stop_loss_usd:'50',scenarios:[],warnings:[]},plan_id:'plan1',analysis_reply:analysis,analysis_snapshot_id:sid,analysis_as_of_utc:at});
  if(p==='/api/trading/plans')return json({status:'AVAILABLE',items:[{...plan,...plan.draft}],total:1});
  if(p==='/api/trading/plans/plan1')return json(plan);
  if(p==='/api/trading/plans/plan1/review'){plan={...plan,revision:plan.revision+1,review_note:body.note,adherence:body.adherence,lesson:body.lesson};return json(plan);}
  if(p==='/api/trading/calendar')return json({status:'AVAILABLE',events:[]});
  if(p==='/api/trading/alerts'&&m==='GET')return json({status:'AVAILABLE',items:alerts,events,monitor_running:true});
  if(p==='/api/trading/alerts'&&m==='POST'){const a={...body,id:'alert1',revision:1,enabled:true,state:'ACTIVE'};alerts=[a];return json(a);}
  if(p==='/api/trading/alerts/alert1'&&m==='PATCH'){alerts=alerts.map(a=>({...a,revision:a.revision+1,enabled:body.enabled,state:body.enabled?'ACTIVE':'PAUSED'}));return json(alerts[0]);}
  if(p.endsWith('/cancel'))return json({status:'CANCELLED'});
  if(m!=='GET')return r.fulfill({status:403,json:{detail:'All other mutations blocked by synthetic test'}});
  return r.continue();
 });
 await page.goto('/');await expect(page.locator('.ag-center')).toBeVisible();
 return {calls,notify:()=>{events=[{id:'event1',name:'合成觸價提醒',message:'Bid 到達條件，沒有送單。',created_at_utc:new Date().toISOString()}];}};
}
async function fields(page:Page){const p=page.locator('#ag-order-panel');await p.getByRole('button',{name:'做多 BUY',exact:true}).click();await p.getByRole('button',{name:'限價',exact:true}).click();await p.locator('#side-ticket-limit').fill('4000');await p.locator('#side-ticket-sl').fill('3995');await p.locator('#side-ticket-tp').fill('4005');return p;}

test('risk sizing works with blank lot and applies only after explicit fresh recalculation',async({page})=>{
 const {calls}=await setup(page),p=await fields(page);await expect(p.locator('#side-ticket-lot')).toHaveValue('');
 await p.getByText('依可承擔風險反算手數',{exact:true}).click();await p.locator('#side-ticket-risk-budget').fill('50');
 await p.getByRole('button',{name:'計算手數',exact:true}).click();await expect(p).toContainText('試算 0.1 手');await expect(p.locator('#side-ticket-lot')).toHaveValue('');
 await p.getByRole('button',{name:'以最新報價重算並套用手數',exact:true}).click();await expect(p.locator('#side-ticket-lot')).toHaveValue('0.1');
 expect(calls.filter(c=>c.path.endsWith('/risk-size'))).toHaveLength(2);expect(calls.some(c=>c.path.endsWith('/confirm'))).toBe(false);
 await expect(p.getByLabel('帳戶與本筆風險')).toContainText('0.5000%');
});

test('live chart keyboard and pointer edits change only draft and invalidate prior review',async({page})=>{
 const {calls}=await setup(page),p=await fields(page);await p.locator('#side-ticket-lot').fill('0.1');
 await p.getByRole('button',{name:'檢查 DEMO 委託',exact:true}).click();await expect(page.getByRole('button',{name:'確認送出 DEMO 委託',exact:true})).toBeVisible();
 await page.getByRole('tab',{name:'即時圖',exact:true}).click();const handle=page.getByRole('button',{name:'調整草稿停損',exact:true});await expect(handle).toBeVisible();
 await handle.press('ArrowDown');await page.getByRole('tab',{name:'下單',exact:true}).click();await expect(p.locator('#side-ticket-sl')).toHaveValue('3994.99');await expect(page.getByRole('button',{name:'確認送出 DEMO 委託',exact:true})).toHaveCount(0);
 await page.getByRole('tab',{name:'即時圖',exact:true}).click();await expect(handle).toBeVisible();const box=(await handle.boundingBox())!;
 await page.mouse.move(box.x+box.width/2,box.y+box.height/2);await page.mouse.down();await page.mouse.move(box.x+box.width/2,box.y+box.height/2-20,{steps:5});await page.mouse.up();
 await page.getByRole('tab',{name:'下單',exact:true}).click();await expect(p.locator('#side-ticket-sl')).not.toHaveValue('3994.99');expect(calls.some(c=>c.path.endsWith('/confirm'))).toBe(false);
});

test('plan preserves frozen evidence and review across reload',async({page})=>{
 const {calls}=await setup(page);await page.getByRole('button',{name:'計畫',exact:true}).click();const tools=page.getByLabel('交易計畫與提醒');
 await tools.getByRole('button',{name:/買進 0.1 手/}).click();await expect(tools).toContainText('原始交易理由');await expect(tools).toContainText('當時為區間內反彈');
 await tools.getByLabel('復盤筆記',{exact:true}).fill('有等到條件，保留原分析');await expect(tools.getByLabel('是否遵守計畫')).toHaveCount(1);await tools.getByLabel('是否遵守計畫').selectOption('YES');await tools.getByRole('button',{name:'儲存復盤',exact:true}).click();await expect(tools).toContainText('復盤已儲存');
 await page.reload();await page.getByRole('button',{name:'計畫',exact:true}).click();await tools.getByRole('button',{name:/買進 0.1 手/}).click();await expect(tools.getByLabel('復盤筆記',{exact:true})).toHaveValue('有等到條件，保留原分析');await expect(tools).toContainText('原始交易理由');
 await tools.getByText('查看當時五分／一小時 K 線',{exact:true}).click();await expect(tools.locator('canvas').first()).toBeVisible();
 expect(calls.some(c=>c.path.endsWith('/discuss'))).toBe(false);
});

test('reminder creation pause and notification dedup work without orders or inference',async({page})=>{
 const {calls,notify}=await setup(page);await page.getByRole('button',{name:'提醒',exact:true}).click();const tools=page.getByLabel('交易計畫與提醒');
 await tools.getByText('建立條件提醒',{exact:true}).click();await tools.getByLabel('提醒名稱').fill('到價再觀察');await tools.getByLabel('提醒價位').fill('4010');await tools.getByRole('button',{name:'建立提醒',exact:true}).click();await expect(tools).toContainText('到價再觀察 · 已啟用');
 await tools.getByRole('button',{name:'暫停',exact:true}).click();await expect(tools).toContainText('到價再觀察 · 已暫停');notify();await expect(page.locator('[data-sonner-toast]')).toContainText('合成觸價提醒',{timeout:10000});
 await page.reload();await expect(page.locator('[data-sonner-toast]')).toHaveCount(0);expect(calls.some(c=>c.path.endsWith('/confirm')||c.path.endsWith('/discuss')||c.path.includes('live-chat'))).toBe(false);
});
