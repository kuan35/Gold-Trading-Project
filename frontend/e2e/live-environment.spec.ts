import {test,expect} from '@playwright/test';

const at='2026-11-10T00:00:00Z';
const account=(balance:string)=>({status:'CURRENT',currency:'USD',balance,equity:balance,
  pnl_status:'CURRENT',net_unrealized_pnl:'0',xau_net_unrealized_pnl:'0',account_last4:'TEST',
  account_leverage:'30',positions:[],pending_orders:[],all_positions_count:0,
  all_pending_orders_count:0,updated_at_utc:at});
const market=(environment:'demo'|'live',balance:string)=>({environment,
  source:`ctrader_${environment}_xauusd`,connection_status:'CONNECTED',token_scope:environment==='live'?'ACCOUNTS':'TRADE',
  order_connection:environment==='demo',symbol:{lot_size_cents:10000,min_volume_cents:100,
    max_volume_cents:100000,step_volume_cents:100,digits:2},
  quote:{status:'CURRENT',bid:'4000',ask:'4000.20',age_seconds:0,source_time_utc:at},account:account(balance)});

test('LIVE zero balance stays read only and never reads DEMO chart or activity while switching',async({page})=>{
  const paths:string[]=[];
  await page.route('**/api/**',async route=>{
    const path=new URL(route.request().url()).pathname;
    paths.push(`${route.request().method()} ${path}`);
    const json=(value:unknown)=>route.fulfill({json:value});
    if(path==='/api/broker/market')return json(market('demo','10000'));
    if(path==='/api/live/market')return json(market('live','0'));
    if(path==='/api/live/activity')return json({environment:'live',source:'ctrader_live_xauusd',
      connection_status:'CONNECTED',account_scope:'CURRENT',updated_at_utc:at,
      submissions:{items:[],total:0,has_more:false,offset:0,limit:50},
      broker_orders:{status:'CURRENT',items:[],has_more:false},broker_deals:{status:'CURRENT',items:[],has_more:false}});
    if(path==='/api/live/trading/plans')return json({status:'AVAILABLE',items:[],total:0,limit:20,offset:0});
    if(path==='/api/live/bars')return json({environment:'live',source:'ctrader_live_xauusd',
      status:'UNAVAILABLE',interval:new URL(route.request().url()).searchParams.get('interval'),closed_only:true,bars:[]});
    if(path.endsWith('/chart-stream'))return route.abort();
    return route.fulfill({status:503,json:{detail:'synthetic test blocks all other requests'}});
  });
  await page.goto('/');
  const environment=page.getByLabel('交易環境').first();
  await expect(environment).toHaveValue('demo');
  await environment.selectOption('live');
  await expect(environment).toHaveValue('live');
  await expect(page.getByText('LIVE 為真實資金',{exact:false})).toBeVisible();
  await expect(page.getByRole('button',{name:'檢查 LIVE 委託'})).toBeDisabled();
  const before=paths.length;
  await page.getByRole('tab',{name:'即時圖'}).click();
  await expect.poll(()=>paths.slice(before).some(p=>p.includes('/api/live/bars'))).toBe(true);
  expect(paths.slice(before).some(p=>p.includes('/api/broker/bars')||p.includes('/api/broker/chart-stream'))).toBe(false);
  await page.getByRole('tab',{name:'紀錄',exact:true}).click();
  await expect.poll(()=>paths.some(p=>p==='GET /api/live/trading/plans')).toBe(true);
  expect(paths.some(p=>p.includes('/api/trading/plans'))).toBe(false);
  await page.getByRole('tab',{name:'券商紀錄',exact:true}).click();
  await expect.poll(()=>paths.some(p=>p.includes('/api/live/activity'))).toBe(true);
  expect(paths.some(p=>p.startsWith('POST /api/live/drafts'))).toBe(false);
  await environment.selectOption('demo');
  await expect(environment).toHaveValue('demo');
});

test('LIVE missing account configuration is visible instead of endless connecting',async({page})=>{
  await page.route('**/api/**',route=>{
    const path=new URL(route.request().url()).pathname;
    if(path==='/api/broker/market')return route.fulfill({json:market('demo','10000')});
    if(path==='/api/live/market')return route.fulfill({json:{...market('live','0'),
      connection_status:'ACCOUNT_ID_REQUIRED',account:null,quote:{status:'UNAVAILABLE',bid:null,ask:null,source_time_utc:null,age_seconds:null}}});
    return route.fulfill({status:503,json:{detail:'synthetic test blocks all other requests'}});
  });
  await page.goto('/');
  await page.getByLabel('交易環境').first().selectOption('live');
  await expect(page.getByText('LIVE 設定待完成')).toBeVisible();
  await expect(page.locator('[data-tip="LIVE 尚未設定 Open API 帳戶 ID"]')).toBeVisible();
  await expect(page.getByRole('button',{name:'檢查 LIVE 委託'})).toBeDisabled();
});
