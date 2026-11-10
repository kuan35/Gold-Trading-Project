import {test,expect,type Page} from '@playwright/test';
async function setup(page:Page,{unknown=false,readOnly=false}={}){
 let applied=false,statusChecks=0;const mutations:{path:string;body:any}[]=[];
 await page.route('**/api/**',async route=>{
  const path=new URL(route.request().url()).pathname,json=(value:unknown)=>route.fulfill({json:value});
  if(path==='/api/broker/market')return json({environment:'demo',connection_status:'CONNECTED',token_scope:readOnly?'ACCOUNTS':'TRADE',order_connection:!readOnly,symbol:{lot_size_cents:10000,min_volume_cents:100,max_volume_cents:100000,step_volume_cents:100,digits:2},quote:{status:'CURRENT',bid:'4000',ask:'4000.20',age_seconds:0,source_time_utc:'2000-01-01T00:00:00Z'},account:{status:'CURRENT',pnl_status:'CURRENT',currency:'EUR',balance:'10000',equity:'10012',positions:[{id:'123',side:'BUY',volume_units:'10',lot:'0.10',entry:'3990',sl:applied?'3985':'3980',tp:'4020',net_pnl:'12.00',price_return_pct:'0.2500',margin_roi_pct:'12.0000',actual_margin_roi_pct:'12.0000',margin_return_source:'BROKER_POSITION',used_margin:'100',return_currency:'EUR'}],pending_orders:[],all_positions_count:1,all_pending_orders_count:0,updated_at_utc:applied?'2000-01-01T00:00:02Z':'2000-01-01T00:00:00Z'}});
  if(path==='/api/assistant/status')return json({configured:false,provider:'claude_code',model:'sonnet'});
  if(path==='/api/broker/drafts/protection-test/status'){statusChecks++;applied=true;return json({status:'APPLIED',status_observed_at_utc:'2000-01-01T00:00:01Z'});}
  if(route.request().method()==='POST'){
   mutations.push({path,body:route.request().postDataJSON()});
   if(path==='/api/broker/positions/123/protection-draft')return json({id:'protection-test',revision:1,position_id:'123',sl:'3985',tp:'4020',explanation:'合成變更：只改停損，保留停利'});
   if(path==='/api/broker/drafts/protection-test/confirm'){applied=!unknown;return json({status:unknown?'UNKNOWN':'APPLIED',status_observed_at_utc:'2000-01-01T00:00:01Z'});}
   if(path.endsWith('/cancel'))return json({status:'CANCELLED'});
   return route.fulfill({status:403,json:{detail:'Synthetic test blocks other mutations'}});
  }
  if(path==='/api/broker/chart-stream')return route.abort();return route.continue();
 });
 await page.goto('/');await page.locator('.ag-drawer').getByRole('tab',{name:'帳戶',exact:true}).click();
 const card=page.locator('.ag-drawer').getByRole('article',{name:'持倉 123'});
 await expect(card).toBeVisible();return {card,mutations,statusChecks:()=>statusChecks};
}
test('sidebar filled position edits only the requested stop and requires manual confirmation',async({page})=>{
 const {card,mutations}=await setup(page);
 await expect(card).toContainText('12.00 EUR');await expect(card.getByRole('group',{name:'持倉報酬率'})).toContainText('持倉報酬率 +12.0000%');await expect(card.getByText('價格報酬率 +0.2500%',{exact:true})).not.toBeVisible();await card.getByRole('button',{name:'修改停損／停利',exact:true}).click();
 const dialog=page.getByRole('dialog',{name:'修改停損停利',exact:true});
 await dialog.getByLabel('停損修改方式').selectOption('SET');
 await expect(dialog.getByLabel('停損指定價')).toHaveValue('3980');
 await dialog.getByLabel('停損指定價').fill('3985');await dialog.getByRole('button',{name:'檢查變更'}).click();
 expect(mutations[0]).toEqual({path:'/api/broker/positions/123/protection-draft',body:{sl:'3985'}});
 expect(mutations.some(m=>m.path.endsWith('/confirm'))).toBe(false);await expect(dialog).toContainText('停利 4020');
 await dialog.getByRole('button',{name:'確認修改停損／停利',exact:true}).click();
 await expect(dialog).not.toBeVisible();await expect(card.getByText('停損 3985 · 停利 4020',{exact:true})).toBeVisible();
 expect(mutations.filter(m=>m.path.endsWith('/confirm'))).toHaveLength(1);
 await page.screenshot({path:'test-results/position-protection.png'});
});
test('unknown stop update remains locked and polls until reconciled instead of resending',async({page})=>{
 const {card,mutations,statusChecks}=await setup(page,{unknown:true});
 await card.getByRole('button',{name:'修改停損／停利',exact:true}).click();
 const dialog=page.getByRole('dialog',{name:'修改停損停利',exact:true});
 await dialog.getByLabel('停損修改方式').selectOption('SET');await dialog.getByLabel('停損指定價').fill('3985');
 await dialog.getByRole('button',{name:'檢查變更'}).click();await dialog.getByRole('button',{name:'確認修改停損／停利',exact:true}).click();
 await expect(card.getByRole('button',{name:'修改停損／停利',exact:true})).toBeDisabled();
 await expect.poll(statusChecks).toBeGreaterThan(0);await expect(card.getByText('停損 3985 · 停利 4020',{exact:true})).toBeVisible();
 await expect(card.getByRole('button',{name:'修改停損／停利',exact:true})).toBeEnabled();
 expect(mutations.filter(m=>m.path.endsWith('/confirm'))).toHaveLength(1);
});
test('read-only accounts show position fields but cannot change protection',async({page})=>{
 const {card,mutations}=await setup(page,{readOnly:true});
 await expect(card.getByRole('button',{name:'修改停損／停利',exact:true})).toBeDisabled();expect(mutations).toHaveLength(0);
});
