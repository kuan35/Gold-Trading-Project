import {test,expect,type Page} from '@playwright/test';

const questionA='現在該做多還是做空？',questionB='做多還是做空？';
const reply=(text:string)=>({provider:'claude_market_analysis',model:'sonnet',llm_status:'ok',market_status:'CURRENT',
 as_of_utc:'2000-01-01T00:00:00Z',source:'synthetic',message:text,draft:null,followups:[],evidence:[],
 sections:[{title:'綜合建議',text,fact_ids:['f5.trend'],source:'model'}]});

async function setup(page:Page,holdInterpret=false){
 const posts:{path:string;body:any}[]=[],gates:(()=>void)[]=[];
 await page.route('**/api/**',async route=>{
  const path=new URL(route.request().url()).pathname;
  if(path==='/api/assistant/status')return route.fulfill({json:{provider:'claude_code',configured:true,enabled:true,model:'sonnet'}});
  if(path==='/api/broker/market')return route.fulfill({json:{environment:'demo',connection_status:'DISCONNECTED',order_connection:false,
   quote:{status:'UNAVAILABLE',bid:null,ask:null},account:null}});
  if(path==='/api/broker/chart-stream')return route.abort();
  if(route.request().method()==='POST'){
   const body=route.request().postDataJSON();posts.push({path,body});
   if(path==='/api/assistant/live-chat'||path==='/api/assistant/interpret'){
    const index=posts.length-1;
    if((path.endsWith('/interpret')&&holdInterpret)||(path.endsWith('/live-chat')&&!holdInterpret))await new Promise<void>(resolve=>gates[index]=resolve);
    const json=path.endsWith('/interpret')?{intent:'PREPARE',patch:{side:'BUY',order_type:'MARKET',lot:'0.2'},proposal:{},
     message:'合成的準備委託',analysis_side:'BUY',input_revision:body.input_revision}:reply('合成回覆 '+body.message);
    try{await route.fulfill({json});}catch{/* A cancelled/deleted thread may abort this fixture. */}return;
   }
   return route.fulfill({status:403,json:{detail:'All other mutations blocked'}});
  }
  return route.continue(); // Existing read-only app bootstrap only.
 });
 await page.goto('/');await expect(page.locator('.ag-center')).toBeVisible();
 return {posts,release:(index:number)=>gates[index]?.()};
}

test('a pending answer does not lock navigation, ticket fields or returning to the original chat',async({page})=>{
 const {posts,release}=await setup(page);
 await page.getByRole('button',{name:questionA,exact:true}).click();await expect.poll(()=>posts.length).toBe(1);
 const live=page.locator('.ag-rail').getByRole('button',{name:'即時看盤',exact:true});
 await expect(live).toBeEnabled();await live.click();
 await page.locator('.ag-rail').getByRole('button',{name:'交易對話',exact:true}).click();
 await expect(page.locator('.ag-thinking')).toBeVisible();
 await page.locator('#side-ticket-lot').fill('0.3');
 release(0);await expect(page.locator('.ag-log')).toContainText('合成回覆 '+questionA);
 await expect(page.locator('#side-ticket-lot')).toHaveValue('0.3');
 expect(posts.some(p=>p.path.startsWith('/api/broker/drafts'))).toBe(false);
});

test('concurrent chats receive only their own answers and preserve the background answer after reload',async({page})=>{
 const {posts,release}=await setup(page);
 await page.getByRole('button',{name:questionA,exact:true}).click();await expect.poll(()=>posts.length).toBe(1);
 const create=page.locator('.ag-rail').getByRole('button',{name:'新對話',exact:true});
 await expect(create).toBeEnabled();await create.click();
 await page.locator('#conversation-message').fill(questionB);await page.getByRole('button',{name:'送出對話',exact:true}).click();
 await expect.poll(()=>posts.length).toBe(2);expect(posts[0].body.conversation_id).not.toBe(posts[1].body.conversation_id);
 release(0);await expect(page.locator('.ag-log')).not.toContainText('合成回覆 '+questionA);
 await expect(page.locator('.ag-thinking')).toBeVisible();
 release(1);await expect(page.locator('.ag-log')).toContainText('合成回覆 '+questionB);
 await page.locator('.ag-rail').getByRole('button',{name:'對話紀錄',exact:true}).click();
 await page.locator('.pd-history-open').filter({hasText:questionA}).click();
 await expect(page.locator('.ag-log')).toContainText('合成回覆 '+questionA);
 await expect(page.locator('.ag-log')).not.toContainText('合成回覆 '+questionB);
 await page.reload();await expect(page.locator('.ag-log')).toContainText('合成回覆 '+questionA);
});

test('a delayed interpretation from another chat cannot edit the current order',async({page})=>{
 const {posts,release}=await setup(page,true);
 await page.locator('#conversation-message').fill('買進0.2手');await page.getByRole('button',{name:'送出對話',exact:true}).click();
 await expect.poll(()=>posts.length).toBe(1);
 await page.locator('.ag-rail').getByRole('button',{name:'新對話',exact:true}).click();
 release(0);await expect.poll(()=>posts.length).toBe(2);
 await expect(page.locator('#side-ticket-lot')).toHaveValue('');
 await expect(page.locator('#ag-order-panel').getByRole('button',{name:'做多 BUY',exact:true})).not.toHaveClass(/active|selected/);
 await expect(page.locator('.ag-log')).not.toContainText('合成回覆');
 expect(posts.some(p=>p.path.startsWith('/api/broker/drafts'))).toBe(false);
});

test('stopping a response releases the current chat and cannot replace its newer answer',async({page})=>{
 const {posts,release}=await setup(page);
 await page.getByRole('button',{name:questionA,exact:true}).click();await expect.poll(()=>posts.length).toBe(1);
 await page.getByRole('button',{name:'停止回覆',exact:true}).click();
 await expect(page.locator('.ag-thinking')).toHaveCount(0);await expect(page.locator('.ag-log')).toContainText('已停止這次回覆');
 await page.locator('#conversation-message').fill(questionB);await page.getByRole('button',{name:'送出對話',exact:true}).click();
 await expect.poll(()=>posts.length).toBe(2);release(0);release(1);
 await expect(page.locator('.ag-log')).toContainText('合成回覆 '+questionB);
 await expect(page.locator('.ag-log')).not.toContainText('合成回覆 '+questionA);
});

test('deleting a pending conversation prevents a late response from recreating it',async({page})=>{
 const {posts,release}=await setup(page);
 await page.getByRole('button',{name:questionA,exact:true}).click();await expect.poll(()=>posts.length).toBe(1);
 await page.locator('.ag-rail').getByRole('button',{name:'對話紀錄',exact:true}).click();
 await page.getByRole('button',{name:'管理對話 '+questionA,exact:true}).click();
 await page.getByRole('button',{name:'刪除對話',exact:true}).click();await page.getByRole('button',{name:'確認刪除此對話',exact:true}).click();
 await page.getByRole('dialog',{name:'對話紀錄',exact:true}).getByRole('button',{name:'關閉對話紀錄',exact:true}).click();
 release(0);await expect(page.locator('.ag-user')).toHaveCount(0);
 await page.reload();await page.locator('.ag-rail').getByRole('button',{name:'對話紀錄',exact:true}).click();
 await expect(page.locator('.pd-history-open').filter({hasText:questionA})).toHaveCount(0);
});
