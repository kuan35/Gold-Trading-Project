import {test,expect,type Page} from '@playwright/test';
const reply={provider:'claude_market_analysis',model:'sonnet',llm_status:'ok',market_status:'CURRENT',as_of_utc:'2000-01-01T00:00:00Z',source:'synthetic',message:'合成回覆',followups:[],evidence:[],draft:null,sections:[{title:'先回答你的問題',text:'短線正在回檔，但較長週期仍有支持。'.repeat(25),fact_ids:['f5.trend'],source:'model'}]};
async function setup(page:Page){
 const requests:{path:string;body:any}[]=[];
 await page.route('**/api/**',async r=>{
  const path=new URL(r.request().url()).pathname;
  if(r.request().method()!=='GET'){
   const body=r.request().postDataJSON();requests.push({path,body});
   return r.fulfill({json:path.endsWith('/interpret')?{intent:'DISCUSS',patch:{},proposal:{},message:'僅討論，不修改草稿',analysis_side:body.analysis_side??null,input_revision:body.input_revision}:reply});
  }
  if(path==='/api/broker/chart-stream')return r.abort();
  if(path==='/api/broker/market')return r.fulfill({json:{environment:'demo',connection_status:'DISCONNECTED',order_connection:false,quote:{status:'UNAVAILABLE',bid:null,ask:null},account:null}});
  if(path.startsWith('/api/assistant/config'))return r.fulfill({json:{configured:false,enabled:false,provider:'program',reason:'synthetic_test',model:'program'}});
  return r.continue(); // Read-only app bootstrap; never allow a mutation through.
 });
 await page.goto('/');await expect(page.locator('.ag-center')).toBeVisible();return requests;
}
test('resize changes actual height in both directions, persists and resets',async({page})=>{
 await setup(page);const handle=page.getByRole('separator',{name:'調整聊天高度'}),log=page.locator('.ag-log');
 const initial=await log.evaluate(e=>e.getBoundingClientRect().height);
 for(const delta of [120,-80]){
  const before=await log.evaluate(e=>e.getBoundingClientRect().height),box=(await handle.boundingBox())!;
  await page.mouse.move(box.x+box.width/2,box.y+box.height/2);await page.mouse.down();await page.mouse.move(box.x+box.width/2,box.y+box.height/2+delta,{steps:10});await page.mouse.up();
  await expect.poll(()=>log.evaluate(e=>e.getBoundingClientRect().height)).toBeCloseTo(before+delta,0);
 }
 await page.waitForTimeout(250);await page.reload();await expect.poll(()=>log.evaluate(e=>e.getBoundingClientRect().height)).toBeCloseTo(initial+40,0);
 await page.getByRole('button',{name:'還原大小',exact:true}).click();await expect(page.locator('.ag-desk')).not.toHaveClass(/ag-sized/);
});
test('beginner and macro starters use knowledge endpoint with exact displayed question',async({page})=>{
 const requests=await setup(page);const q='黃金交易新手要先了解什麼？';await page.getByRole('button',{name:'新手教學 '+q}).click();
 await expect.poll(()=>requests.length).toBe(1);expect(requests[0].path).toBe('/api/assistant/gold-chat');expect(requests[0].body.message).toBe(q);
 await expect(page.locator('.ag-user')).toHaveText(q);
 const macro='最近有哪些總經事件會影響黃金？';await page.getByRole('button',{name:macro,exact:true}).click();
 await expect.poll(()=>requests.length).toBe(2);expect(requests[1].path).toBe('/api/assistant/gold-chat');expect(requests[1].body.message).toBe(macro);
});
test('market starter is neutral, reply has short headings and expandable uncut prose',async({page})=>{
 const requests=await setup(page),q='目前黃金盤面有哪些偏多與偏空訊號？';await page.getByRole('button',{name:'看多空訊號 '+q}).click();
 await expect(page.locator('.ag-answer-prose')).toBeVisible();expect(requests.map(r=>r.body.message)).toEqual([q,q]);
 expect(requests[1].body.include_cases).toBe(false);expect(requests[1].body.side).toBeUndefined();
 await expect(page.locator('.ag-headline')).toHaveCount(0);await page.getByRole('button',{name:'展開這段',exact:true}).click();
 await expect(page.locator('.ag-answer-prose p').first()).toHaveText(reply.sections[0].text);
});
test('case starter asks direction and prepare only focuses ticket without assuming quantity',async({page})=>{
 const requests=await setup(page);await page.getByRole('button',{name:/準備一筆委託 在右側/}).click();
 await expect(page.getByRole('tab',{name:'下單',exact:true})).toHaveAttribute('aria-selected','true');expect(requests).toHaveLength(0);
 await expect(page.locator('#side-ticket-lot')).toHaveValue('');
 await page.getByRole('button',{name:/找相似案例 先選/}).click();expect(requests).toHaveLength(0);
 await page.getByRole('button',{name:'比較做空案例',exact:true}).click();await expect.poll(()=>requests.length).toBe(2);
 expect(requests[0].body.analysis_side).toBe('SELL');expect(requests[1].body.side).toBe('SELL');expect(requests[1].body.draft.side).toBeNull();
});
