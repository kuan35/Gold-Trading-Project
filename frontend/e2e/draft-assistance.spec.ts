import {test,expect,type Page} from '@playwright/test';
const at='2000-01-01T00:00:00Z',sid='c'.repeat(64);
const program={analysis_ref:'a'.repeat(64),provider:'local_market_rules',model:null,llm_status:'not_requested',market_status:'FROZEN',as_of_utc:at,quote_time_utc:at,snapshot_id:sid,analysis_mode:'draft_snapshot',source:'synthetic',message:'合成程式檢查',draft:null,followups:[],evidence:[],sections:[{title:'程式檢查',text:'合成程式檢查保留',fact_ids:['f5.trend']}]};
const agent={...program,analysis_ref:'b'.repeat(64),provider:'claude_market_analysis',model:'sonnet',llm_status:'ok',sections:[{title:'助手解讀',text:'合成助手依原草稿說明風險，不代為確認。',fact_ids:['draft.risk'],source:'model'}]};
async function setup(page:Page,fail=false){
 let release!:()=>void;const gate=new Promise<void>(r=>release=r),posts:{path:string;body:any}[]=[];
 await page.addInitScript(()=>localStorage.setItem('gold-desk-claude-selection-v1',JSON.stringify({provider:'claude_code',model:'sonnet',effort:'high'})));
 await page.route('**/api/**',async r=>{
  const path=new URL(r.request().url()).pathname;const json=(v:unknown)=>r.fulfill({json:v});
  if(path.startsWith('/api/assistant/analyses/'))return json(path.endsWith('b'.repeat(64))?agent:program);
  if(path==='/api/assistant/snapshots/'+sid+'/charts'){
   const bars=Array.from({length:60},(_,i)=>({time:946660000+i*300,open:4000+i,high:4002+i,low:3999+i,close:4001+i,volume:50}));
   return json({snapshot_id:sid,query:{'5m':bars,'1h':bars.slice(-20)},cases:[],analysis:{as_of_utc:at,frames:{'5m':{bars,layers:[]},'1h':{bars:bars.slice(-20),layers:[]}}}});
  }
  if(path==='/api/assistant/status')return json({configured:true,enabled:true,provider:'claude_code',model:'sonnet',supports_vision:false});
  if(path==='/api/broker/market')return json({environment:'demo',connection_status:'CONNECTED',token_scope:'TRADE',order_connection:true,symbol:{lot_size_cents:10000,min_volume_cents:100,max_volume_cents:100000,step_volume_cents:100,digits:2},quote:{status:'CURRENT',bid:'4000',ask:'4000.20',age_seconds:0,source_time_utc:at},account:{status:'CURRENT',currency:'USD',balance:'10000',equity:'10000',positions:[],pending_orders:[],all_positions_count:0,all_pending_orders_count:0,updated_at_utc:at}});
  if(r.request().method()==='POST'){
   const body=r.request().postDataJSON();posts.push({path,body});
   if(path==='/api/assistant/interpret')return json({intent:'DISCUSS',analysis_side:'BUY',patch:{},proposal:{},message:'合成討論',input_revision:body.input_revision});
   if(path==='/api/assistant/live-chat')return json({...program,market_status:'CURRENT',analysis_mode:'live'});
   if(path==='/api/broker/ticket-preview'){
    const level=(price:string)=>price?{status:'AVAILABLE',reason:null,pnl_usd:((Number(price)-4000)*Number(body.lot)*100).toFixed(2),price_return_pct:((Number(price)-4000)/4000*100).toFixed(4),margin_roi_pct:((Number(price)-4000)/4000*100*200).toFixed(4)}:null;
    return json({status:'AVAILABLE',reason:null,entry_price:'4000',quantity_oz:'50',sl:level(body.sl),tp:level(body.tp),margin:{source:'LEVERAGE_ESTIMATE',amount_usd:'1000.00',leverage:'200',reason:'合成槓桿假設'},basis:'未扣交易成本',quote_time_utc:at});
   }
   if(path==='/api/broker/drafts')return json({id:'synthetic-draft',revision:1,side:'BUY',lot:'0.5',order_type:'LIMIT',price:'4000',sl:'3990',tp:'4020',expires_at_utc:new Date(Date.now()+30000).toISOString(),risk:{before_lot:'0',after_lot:'0.5',stop_loss_usd:'500',scenarios:[],warnings:[]},analysis_reply:program,analysis_snapshot_id:sid,analysis_as_of_utc:at});
   if(path==='/api/assistant/draft-chat'){await gate;try{return fail?await r.fulfill({status:503,json:{detail:'合成模型失敗'}}):await json(agent);}catch{return;}}
   if(path.endsWith('/cancel'))return json({status:'CANCELLED'});
   return r.fulfill({status:403,json:{detail:'All other mutations blocked'}});
  }
  if(path==='/api/broker/chart-stream')return r.abort();return r.continue();
 });
 await page.goto('/');await expect(page.locator('.ag-center')).toBeVisible();
 const panel=page.locator('#ag-order-panel');await panel.getByRole('button',{name:'做多 BUY',exact:true}).click();await expect(page.locator('.ag-thinking')).toHaveCount(0);
 await panel.getByRole('button',{name:'限價',exact:true}).click();await panel.locator('#side-ticket-lot').fill('0.5');await panel.locator('#side-ticket-limit').fill('4000');await panel.locator('#side-ticket-sl').fill('3990');await panel.locator('#side-ticket-tp').fill('4020');
 return {panel,posts,release};
}
test('instant preview shows USD and price returns before checking; agent does not delay review',async({page})=>{
 const {panel,posts,release}=await setup(page);
 await expect(panel.locator('.ticket-level').first()).toContainText('-500.00 USD');await expect(panel.locator('.ticket-level').last()).toContainText('+1000.00 USD');
 await expect(panel.locator('.ticket-level').first()).toContainText('-0.2500%');expect(posts.some(p=>p.path==='/api/broker/drafts')).toBe(false);
 await expect(panel.locator('.ticket-level').first()).toContainText('預估保證金ROI -50.0000%');
 await expect(panel.locator('.ticket-level').last()).toContainText('預估保證金ROI +100.0000%');
 await expect(panel).toContainText('1000.00 USD · 1:200 試算');
 await panel.getByRole('button',{name:'檢查 DEMO 委託',exact:true}).click();
 await expect(page.getByRole('button',{name:'確認送出 DEMO 委託',exact:true})).toBeVisible();
 await expect(page.getByText('助手正在解讀這份固定草稿快照…',{exact:true})).toBeVisible();
 await expect.poll(()=>posts.some(p=>p.path==='/api/assistant/draft-chat')).toBe(true);
 const sent=posts.find(p=>p.path==='/api/assistant/draft-chat')!.body;expect(sent.draft_id).toBe('synthetic-draft');expect(sent.provider).toBe('claude_code');expect(sent.effort).toBe('high');
 release();await expect(page.locator('.ag-log')).toContainText('合成助手依原草稿');expect(posts.some(p=>p.path.endsWith('/confirm'))).toBe(false);
});
test('editing checked fields cancels display of an old agent answer',async({page})=>{
 const {panel,posts,release}=await setup(page);await panel.getByRole('button',{name:'檢查 DEMO 委託',exact:true}).click();
 await expect.poll(()=>posts.some(p=>p.path==='/api/assistant/draft-chat')).toBe(true);
 await panel.locator('#side-ticket-sl').fill('3980');release();
 await expect(page.getByRole('button',{name:'確認送出 DEMO 委託',exact:true})).toHaveCount(0);
 await expect(panel.locator('.ticket-level').first()).toContainText('-1000.00 USD');await expect(page.locator('.ag-log')).not.toContainText('合成助手依原草稿');await expect(page.locator('.ag-log')).toContainText('保留原草稿的程式檢查');
});
test('agent failure retains the successful program check and never submits an order',async({page})=>{
 const {panel,posts,release}=await setup(page,true);await panel.getByRole('button',{name:'檢查 DEMO 委託',exact:true}).click();
 await expect.poll(()=>posts.some(p=>p.path==='/api/assistant/draft-chat')).toBe(true);release();
 await expect(page.locator('.ag-log')).toContainText('助手未能完成解讀，保留程式檢查結果');
 await expect(page.getByRole('button',{name:'確認送出 DEMO 委託',exact:true})).toBeVisible();expect(posts.some(p=>p.path.endsWith('/confirm'))).toBe(false);
});
test('chart opened before agent completion survives model reply and reload',async({page})=>{
 const {panel,posts,release}=await setup(page);await panel.getByRole('button',{name:'檢查 DEMO 委託',exact:true}).click();
 await expect.poll(()=>posts.some(p=>p.path==='/api/assistant/draft-chat')).toBe(true);
 await page.locator('.ag-log').getByRole('button',{name:'看圖',exact:true}).last().click();
 await expect(page.locator('.ag-chart-evidence canvas').first()).toBeVisible();release();
 await expect(page.locator('.ag-log')).toContainText('合成助手依原草稿');
 await page.reload();await expect(page.locator('.ag-chart-evidence canvas').first()).toBeVisible();await expect(page.locator('.ag-log')).toContainText('合成助手依原草稿');
});
test('mobile order overlay has an opaque background instead of blending chat text through fields',async({page})=>{
 await page.setViewportSize({width:390,height:844});const {panel,release}=await setup(page);release();
 await expect(panel).toBeVisible();
 const background=await page.locator('.ag-drawer').evaluate(e=>getComputedStyle(e).backgroundColor);
 expect(background).not.toMatch(/rgba\([^)]*,\s*0\./);
});
