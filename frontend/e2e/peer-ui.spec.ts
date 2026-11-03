import {test,expect,type Page} from '@playwright/test';

// Synthetic account only. All broker mutation endpoints are intercepted in the browser.
async function setup(page:Page){
 const now=new Date().toISOString();
 await page.route('**/api/**',async route=>{
  const url=new URL(route.request().url()),p=url.pathname;
  const json=(value:unknown)=>route.fulfill({contentType:'application/json',body:JSON.stringify(value)});
  if(p==='/api/broker/market')return json({source:'ctrader_demo_xauusd',environment:'demo',connection_status:'CONNECTED',token_scope:'TRADE',order_connection:true,symbol:{lot_size_cents:10000,min_volume_cents:100,step_volume_cents:100,max_volume_cents:100000,digits:2},quote:{status:'CURRENT',bid:'4000',ask:'4000.20',age_seconds:0,source_time_utc:now},account:{status:'CURRENT',pnl_status:'CURRENT',currency:'USD',balance:'10000',equity:'10000',net_unrealized_pnl:'0',xau_net_unrealized_pnl:'0',updated_at_utc:now,positions:[{id:'synthetic-p',side:'BUY',volume_units:'10',lot:'0.10',entry:'3999',sl:null,tp:null,net_pnl:'0'}],pending_orders:[],all_positions_count:1,all_pending_orders_count:0}});
  if(p==='/api/broker/positions/synthetic-p/close-draft')return json({id:'synthetic-close',revision:1,intent:'CLOSE',position_id:'synthetic-p',side:'BUY',lot:'0.10',price:'4000',expires_at_utc:new Date(Date.now()+30000).toISOString(),explanation:'合成介面測試，無真實委託'});
  if(p.startsWith('/api/broker/drafts/synthetic-close/'))return json({status:'UNKNOWN',message:'合成未知回報，無真實委託'});
  if(p==='/api/broker/chart-stream')return route.abort();
  if(p==='/api/broker/bars')return json({source:'synthetic_ui_test',environment:'demo',status:'STALE',interval:url.searchParams.get('interval'),closed_only:true,bars:Array.from({length:30},(_,i)=>({time:1800000000+i*300,open:4000+i,high:4002+i,low:3999+i,close:4001+i,volume:10+i}))});
  if(route.request().method()!=='GET')return json({detail:'Blocked by synthetic UI test'});
  return route.continue();
 });
 await page.goto('/');await expect(page.locator('.ag-center')).toBeVisible();
}

test('mobile command menu offers navigation, new chat and saved history',async({page})=>{
 await page.setViewportSize({width:390,height:844});await setup(page);
 await page.getByRole('button',{name:'開啟指令面板',exact:true}).click();
 await expect(page.getByRole('option',{name:/新增對話/})).toBeVisible();
 await expect(page.getByRole('option',{name:/對話紀錄/})).toBeVisible();
 await page.getByRole('option',{name:/對話紀錄/}).click();
 await expect(page.getByRole('dialog',{name:'對話紀錄',exact:true})).toBeVisible();
});

test('drawer chart explicitly labels retained stale bars and tick activity',async({page})=>{
 await setup(page);await page.getByRole('tab',{name:'即時圖',exact:true}).click();
 await expect(page.locator('.ag-mini-chart')).toContainText('已過期');
 await expect(page.locator('.ag-mini-chart')).toContainText('tick');
});

test('UNKNOWN close result survives closing and switching the account drawer',async({page})=>{
 await setup(page);await page.getByRole('tab',{name:'帳戶',exact:true}).click();
 await page.getByRole('button',{name:'平倉',exact:true}).click();
 await page.getByRole('button',{name:'檢查平倉',exact:true}).click();
 await page.getByRole('button',{name:'確認平倉 DEMO 部位',exact:true}).click();
 await expect(page.locator('.ag-drawer')).toContainText('平倉回報待核對');
 await page.getByRole('tab',{name:'下單',exact:true}).click();
 await page.getByRole('tab',{name:'帳戶',exact:true}).click();
 await expect(page.locator('.ag-drawer')).toContainText('平倉回報待核對');
 await expect(page.getByRole('button',{name:'平倉',exact:true})).toBeDisabled();
 await page.locator('.ag-drawer').getByRole('button',{name:'收合側欄',exact:true}).click();
 await page.getByRole('button',{name:'展開側欄',exact:true}).click();
 await expect(page.locator('.ag-drawer')).toContainText('平倉回報待核對');
});

test('saved analysis, case card and original chart survive conversation switching and reload',async({page})=>{
 const ref='a'.repeat(64),sid='b'.repeat(64),at='2026-11-03T00:00:00Z';
 const bars=Array.from({length:60},(_,i)=>({time:1793652000+i*300,open:4000+i/10,high:4002+i/10,low:3999+i/10,close:4001+i/10,volume:20}));
 const reply={analysis_ref:ref,snapshot_id:sid,provider:'program',model:null,llm_status:'disabled',market_status:'FROZEN',source:'synthetic_ui_test',as_of_utc:at,quote_time_utc:null,message:'合成原始盤面',draft:null,followups:[],sections:[{title:'五分鐘',text:'合成原始盤面',fact_ids:['f5.trend']}],evidence:[],case_comparison:{status:'PASSED',label:'符合條件',reason:'合成測試',method:'context_contract_v1',side:'BUY',snapshot_id:sid,query_as_of_utc:1793669700,query_state:{event:'區間內',tail_direction:'上行'},counts:{eligible:3,passed:1,displayed:1},cases:[{ref:'合成案例甲',event:'區間內',tail_direction:'上行',similarities:['走勢接近'],differences:['波動不同'],metrics:[]}],rejections:[]}};
 await page.addInitScript(({ref,sid,at})=>{if(!localStorage.getItem('gold-desk-conversations-v1'))localStorage.setItem('gold-desk-conversations-v1',JSON.stringify({version:3,activeId:'A',items:[{id:'A',title:'合成原分析',updatedAt:2,turns:[{question:'原始查詢',answer:'合成原始盤面',at,analysis_ref:ref}],chart:{id:sid,analysis_ref:ref,mode:'analysis',period:'5m'}},{id:'B',title:'另一串',updatedAt:1,turns:[{question:'另一串問題',answer:'另一串回覆',at}]}]}));},{ref,sid,at});
 await setup(page);
 await page.route('**/api/assistant/analyses/'+ref,r=>r.fulfill({contentType:'application/json',body:JSON.stringify(reply)}));
 await page.route('**/api/assistant/snapshots/'+sid+'/charts',r=>r.fulfill({contentType:'application/json',body:JSON.stringify({snapshot_id:sid,query_as_of_utc:1793669700,query:{'5m':bars,'1h':bars.slice(-20)},cases:[],analysis:{as_of_utc:at,frames:{'5m':{bars,layers:[]},'15m':{bars,layers:[]},'1h':{bars:bars.slice(-20),layers:[]}}}})}));
 await page.reload();await expect(page.locator('.ag-log')).toContainText('合成案例甲');
 await expect(page.locator('.ag-chart-evidence canvas').first()).toBeVisible();
 await page.locator('.ag-rail').getByRole('button',{name:'對話紀錄',exact:true}).click();
 await page.getByRole('button',{name:/另一串/}).first().click();
 await expect(page.locator('.ag-log')).toContainText('另一串回覆');
 await page.locator('.ag-rail').getByRole('button',{name:'對話紀錄',exact:true}).click();
 await page.getByRole('button',{name:/合成原分析/}).first().click();
 await expect(page.locator('.ag-log')).toContainText('合成案例甲');
 await expect(page.locator('.ag-chart-evidence canvas').first()).toBeVisible();
 await page.reload();await expect(page.locator('.ag-log')).toContainText('合成案例甲');
 await expect(page.locator('.ag-chart-evidence canvas').first()).toBeVisible();
});
