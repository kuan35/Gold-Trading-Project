import {test,expect,type Page} from '@playwright/test';
async function setup(page:Page,{unknown=false,raced=false,readOnly=false}={}){
 let cancelled=false,statusChecks=0;const posts:{path:string;body:any}[]=[];
 await page.route('**/api/**',async route=>{
  const path=new URL(route.request().url()).pathname,json=(v:unknown)=>route.fulfill({json:v});
  if(path==='/api/broker/market')return json({environment:'demo',connection_status:'CONNECTED',token_scope:readOnly?'ACCOUNTS':'TRADE',order_connection:!readOnly,symbol:{lot_size_cents:10000,min_volume_cents:100,max_volume_cents:100000,step_volume_cents:100,digits:2},quote:{status:'CURRENT',bid:'4000',ask:'4000.20',age_seconds:0,source_time_utc:'2000-01-01T00:00:00Z'},account:{status:'CURRENT',currency:'USD',balance:'10000',equity:'10000',positions:[],pending_orders:cancelled?[]:[{id:'456',intent:'OPEN',position_id:null,side:'BUY',volume_units:'50',lot:'0.5',order_type:'LIMIT',limit_price:'3990',sl:'3980',tp:'4020',status:'ACCEPTED'}],all_positions_count:0,all_pending_orders_count:cancelled?0:1,updated_at_utc:cancelled?'2000-01-01T00:00:02Z':'2000-01-01T00:00:00Z'}});
  if(path==='/api/assistant/status')return json({configured:false,provider:'claude_code',model:'sonnet'});
  if(path==='/api/broker/drafts/cancel-test/status'){statusChecks++;cancelled=true;return json({status:'CANCELLED',order_id:'456',status_observed_at_utc:'2000-01-01T00:00:01Z'});}
  if(route.request().method()==='POST'){
   posts.push({path,body:route.request().postDataJSON()});
   if(path==='/api/broker/pending/456/cancel-draft')return raced?route.fulfill({status:409,json:{detail:'掛單已成交、取消或變更，請刷新紀錄'}}):json({id:'cancel-test',revision:1,order_id:'456',side:'BUY',lot:'0.5',limit_price:'3990',expires_at_utc:new Date(Date.now()+30000).toISOString(),explanation:'取消這筆尚未成交的進場限價單'});
   if(path==='/api/broker/drafts/cancel-test/confirm'){cancelled=!unknown;return json({status:unknown?'UNKNOWN':'CANCELLED',order_id:'456',status_observed_at_utc:'2000-01-01T00:00:01Z'});}
   if(path.endsWith('/cancel'))return json({status:'CANCELLED'});
   return route.fulfill({status:403,json:{detail:'Synthetic tests block all other mutations'}});
  }
  if(path==='/api/broker/chart-stream')return route.abort();return route.continue();
 });
 await page.goto('/');const drawer=page.locator('.ag-drawer');await drawer.getByRole('tab',{name:'帳戶',exact:true}).click();await drawer.getByRole('tab',{name:'待成交 (1)',exact:true}).click();
 return {drawer,posts,statusChecks:()=>statusChecks};
}
test('submitted entry limit order has an accessible cancel action without requiring a position',async({page})=>{
 const {drawer,posts}=await setup(page);await drawer.getByRole('button',{name:'取消掛單',exact:true}).click();
 const dialog=page.getByRole('dialog',{name:'取消待成交委託',exact:true});await expect(dialog).toContainText('3990');
 expect(posts.filter(p=>p.path.endsWith('/confirm'))).toHaveLength(0);
 await dialog.getByRole('button',{name:'確認取消掛單',exact:true}).click();
 await expect(drawer.getByRole('tab',{name:'待成交 (0)',exact:true})).toBeVisible();
 expect(posts.filter(p=>p.path.endsWith('/confirm'))).toHaveLength(1);
 expect(posts.some(p=>p.path.includes('/close-draft'))).toBe(false);
 await page.screenshot({path:'test-results/pending-cancel.png'});
});
test('unknown cancellation blocks another send and polls the original cancellation receipt',async({page})=>{
 const {drawer,posts,statusChecks}=await setup(page,{unknown:true});await drawer.getByRole('button',{name:'取消掛單',exact:true}).click();
 await page.getByRole('dialog',{name:'取消待成交委託'}).getByRole('button',{name:'確認取消掛單',exact:true}).click();
 await expect(drawer.getByRole('button',{name:'取消掛單',exact:true})).toBeDisabled();
 await expect.poll(statusChecks).toBeGreaterThan(0);await expect(drawer.getByRole('tab',{name:'待成交 (0)',exact:true})).toBeVisible();
 expect(posts.filter(p=>p.path.endsWith('/confirm'))).toHaveLength(1);
});
test('a filled or changed pending order is not treated as cancelled',async({page})=>{
 const {drawer,posts}=await setup(page,{raced:true});await drawer.getByRole('button',{name:'取消掛單',exact:true}).click();
 const dialog=page.getByRole('dialog',{name:'取消待成交委託'});await expect(dialog.getByRole('alert')).toContainText('掛單已成交');
 await expect(dialog.getByRole('button',{name:'確認取消掛單',exact:true})).toHaveCount(0);
 expect(posts.some(p=>p.path.endsWith('/confirm'))).toBe(false);
});
test('read-only account cannot cancel a pending order',async({page})=>{
 const {drawer,posts}=await setup(page,{readOnly:true});await expect(drawer.getByRole('button',{name:'取消掛單',exact:true})).toBeDisabled();expect(posts).toHaveLength(0);
});
