import {test,expect,type Page} from '@playwright/test';
import type {State} from '../src/types';
const start=Date.UTC(2020,0,2)/1000,last=Date.UTC(2026,10,4,10)/1000;
const replayState:State={
 mode:'replay',version:1,clock:last,data_source:'synthetic_demo',
 broker_connected:false,llm_enabled:false,
 quote:{bid:'2000',ask:'2000.20',time:last},account:{balance:'10000',equity:'10000'},
 positions:[],orders:[],pending_orders:[],
 market:{change_pct:'0',range_pct:'0',high:'2002',low:'1999',ma20:null,ma60:null},
 data_quality:[],
};
async function setup(page:Page){
 const calls:Array<{path:string;method:string;query:URLSearchParams}>=[];
 let hold=false,failHourly=false,release!:()=>void;const gate=new Promise<void>(r=>release=r);
 await page.route('**/api/**',async r=>{
  const u=new URL(r.request().url()),p=u.pathname,m=r.request().method();calls.push({path:p,method:m,query:u.searchParams});
  if(p==='/api/state')return r.fulfill({json:replayState});
  if(p==='/api/audit')return r.fulfill({json:{source_files:0,total_gold_records:0,period:'synthetic',groups:[],limitations:[],refreshed_at:'2026-01-01T00:00:00Z',source:'synthetic_demo'}});
  if(p==='/api/history/metadata'||p==='/api/history/refresh')return r.fulfill({json:{status:'AVAILABLE',indexing:false,first:start,last,sources:[{id:'reference',label:'參考歷史行情',first:start,last,count:400000}]}});
  if(p==='/api/history/bars'){
   const at=Number(u.searchParams.get('at')),interval=u.searchParams.get('interval')!,span=interval==='1h'?3600:interval==='15m'?900:300;
   if(failHourly&&interval==='1h')return r.fulfill({status:503,json:{detail:'合成讀取失敗'}});
   if(hold&&interval==='5m'){hold=false;await gate;}
   const anchor=Math.floor(at/span)*span,bars=Array.from({length:100},(_,i)=>({time:anchor+(i-70)*span,open:2000,high:2002,low:1999,close:2001}));
   return r.fulfill({json:{status:at<start?'OUT_OF_RANGE':'AVAILABLE',reason:at<start?'日期超出可用範圍':undefined,requested_at:at,source:'reference',source_label:'參考歷史行情',interval,bars:at<start?[]:bars,anchor_time:anchor,shifted:false,has_before:true,has_after:at<last,gaps:[],volume_basis:'來源未提供量'}});
  }
  if(p==='/api/broker/market')return r.fulfill({json:{environment:'demo',connection_status:'DISCONNECTED',order_connection:false,quote:{status:'UNAVAILABLE'},account:null}});
  if(p==='/api/broker/chart-stream')return r.abort();
  if(p==='/api/trading/alerts')return r.fulfill({json:{status:'UNAVAILABLE',items:[],events:[]}});
  if(m!=='GET')return r.fulfill({status:403,json:{detail:'No mutations during history browsing'}});
  return r.continue();
 });
 await page.goto('/');await page.locator('.ag-center').waitFor();await expect(page.locator('.ag-rail button[aria-label="歷史回放"]')).toBeEnabled();if((page.viewportSize()?.width??1440)<1100){await page.getByRole('button',{name:'開啟指令面板',exact:true}).click();await page.getByRole('option',{name:/歷史回放/}).click();}else await page.locator('.ag-rail').getByRole('button',{name:'歷史回放',exact:true}).click();
 await expect(page.getByLabel('完整歷史看盤')).toBeVisible();await expect(page.locator('.history-chart canvas').first()).toBeVisible();
 return {calls,hold:()=>{hold=true;},failHourly:()=>{failHourly=true;},release};
}
test('date jump, timezone, periods and paging never change replay or submit orders',async({page})=>{
 const {calls}=await setup(page);const before=await page.evaluate(()=>fetch('/api/state').then(r=>r.json()).then(s=>({clock:s.clock,version:s.version})));
 await page.getByLabel('歷史查看時間').fill('2021-05-04T14:25');await page.getByRole('button',{name:'跳轉',exact:true}).click();
 await expect.poll(()=>calls.filter(c=>c.path==='/api/history/bars').at(-1)?.query.get('at')).toBe(String(Date.UTC(2021,4,4,6,25)/1000));
 await expect(page.locator('.history-chart-label')).toContainText('2021-05-04');await page.getByLabel('歷史時區').selectOption('UTC');await expect(page.getByLabel('歷史查看時間')).toHaveValue('2021-05-04T06:25');
 await page.getByRole('button',{name:'1 小時',exact:true}).click();await expect(page.locator('.history-chart-label')).toContainText('1h');
 await page.getByRole('button',{name:'更早一段',exact:true}).click();await expect.poll(()=>calls.filter(c=>c.path==='/api/history/bars').at(-1)?.query.get('direction')).toBe('before');
 await page.keyboard.press('ArrowRight');const after=await page.evaluate(()=>fetch('/api/state').then(r=>r.json()).then(s=>({clock:s.clock,version:s.version})));expect(after).toEqual(before);
 expect(calls.filter(c=>c.method!=='GET')).toHaveLength(0);await expect(page.locator('#order-panel')).toHaveCount(0);
 await page.getByRole('button',{name:'原交易演練',exact:true}).click();await expect(page.locator('#order-panel')).toBeVisible();
});
test('a late prior-period response cannot overwrite the latest selection',async({page})=>{
 const control=await setup(page);control.hold();await page.getByLabel('歷史查看時間').fill('2022-02-03T12:00');await page.getByRole('button',{name:'跳轉',exact:true}).click();
 await expect.poll(()=>control.calls.filter(c=>c.path==='/api/history/bars').at(-1)?.query.get('at')).toBe(String(Date.UTC(2022,1,3,4)/1000));
 await page.getByRole('button',{name:'1 小時',exact:true}).click();await expect(page.locator('.history-chart-label')).toContainText('1h');control.release();
 await expect(page.locator('.history-chart-label')).toContainText('1h');await expect(page.locator('.history-chart-label')).toContainText('2022-02-03');
});
test('mobile history controls fit width and chart height stays bounded',async({page})=>{
 await page.setViewportSize({width:390,height:844});await setup(page);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1)).toBe(false);
 const before=await page.locator('.history-chart').boundingBox();await page.getByRole('button',{name:'15 分',exact:true}).click();
 const after=await page.locator('.history-chart').boundingBox();expect(before!.height).toBeLessThan(800);expect(after!.height).toBeCloseTo(before!.height,0);
 await page.getByLabel('歷史查看時間').fill('2020-01-01T12:00');await page.getByRole('button',{name:'跳轉',exact:true}).click();await expect(page.locator('.history-empty')).toContainText('日期超出可用範圍');
});

test('refreshing metadata does not strand an in-flight date jump',async({page})=>{
 const control=await setup(page);control.hold();await page.getByLabel('歷史查看時間').fill('2023-03-06T12:00');await page.getByRole('button',{name:'跳轉',exact:true}).click();
 await expect.poll(()=>control.calls.filter(c=>c.path==='/api/history/bars').at(-1)?.query.get('at')).toBe(String(Date.UTC(2023,2,6,4)/1000));
 await page.getByRole('button',{name:'重新整理資料索引',exact:true}).click();control.release();
 await expect(page.getByRole('button',{name:'跳轉',exact:true})).toBeEnabled();await expect(page.locator('.history-chart-label')).toContainText('2023-03-06 12:00');
});

test('a failed period change never relabels retained five-minute candles as hourly',async({page})=>{
 const control=await setup(page);control.failHourly();await page.getByRole('button',{name:'1 小時',exact:true}).click();
 await expect(page.getByRole('alert')).toContainText('合成讀取失敗');await expect(page.locator('.history-chart-label strong')).toContainText('5m');
 await page.getByRole('button',{name:'更早一段',exact:true}).click();await expect.poll(()=>control.calls.filter(c=>c.path==='/api/history/bars').at(-1)?.query.get('interval')).toBe('5m');
});
