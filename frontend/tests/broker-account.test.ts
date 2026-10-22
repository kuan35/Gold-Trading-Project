import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createElement} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {BrokerAccountView} from '../src/BrokerAccountPanel';
import type {DemoMarket} from '../src/demoMarket';
import type {BrokerActivity} from '../src/brokerActivity';

const market={source:'ctrader_demo_xauusd',environment:'demo',connection_status:'CONNECTED',order_connection:true,token_scope:'TRADE',
 symbol:{lot_size_cents:10000,min_volume_cents:100,max_volume_cents:100000,step_volume_cents:100,digits:2},
 quote:{status:'CURRENT',bid:'4000',ask:'4000.20',source_time_utc:'2026-10-21T00:00:00Z',age_seconds:1},
 account:{status:'CURRENT',balance:'10000',equity:'10012.34',currency:'EUR',
  pnl_status:'CURRENT',pnl_updated_at_utc:'2026-10-21T00:00:00Z',net_unrealized_pnl:'12.34',xau_net_unrealized_pnl:'12.34',
  positions:[{id:'123',side:'SELL',volume_units:'10',lot:'0.10',entry:'4001',sl:null,tp:null,net_pnl:'12.34',gross_pnl:'14.50'}],
  pending_orders:[{id:'456',side:'BUY',volume_units:'10',lot:'0.10',limit_price:'3990',status:'ACCEPTED',order_type:'LIMIT'}],
  all_positions_count:1,all_pending_orders_count:1,updated_at_utc:'2026-10-21T00:00:00Z'}} as DemoMarket;
const activity={source:'ctrader_demo_xauusd',environment:'demo',connection_status:'CONNECTED',account_scope:'CURRENT',updated_at_utc:'now',
 submissions:{items:[{draft_id:'d',client_order_id:'gd-a',created_at_utc:'2026-10-21T00:00:00Z',side:'BUY',lot:'.10',order_type:'MARKET',status:'UNKNOWN',account_scope:'CURRENT'}],total:51,has_more:true,offset:0,limit:50},
 broker_orders:{status:'CURRENT',items:[],has_more:false},broker_deals:{status:'CURRENT',has_more:true,items:[{id:'7',side:'SELL',lot:'.10',status:'FILLED',role:'CLOSE',execution_price:'4000',realized_gross_pnl:'-4.25',commission:'-.25',swap:'0',executed_at_utc:'2026-10-21T00:00:00Z'}]}} as BrokerActivity;

test('broker position panel displays actual deposit-currency pnl and quote side, not replay balance',()=>{
 const html=renderToStaticMarkup(createElement(BrokerAccountView,{market,activity,tab:'positions'}));
 assert.match(html,/12.34/);assert.match(html,/EUR/);assert.match(html,/4000.20/);
 assert.match(html,/浮動淨損益/);assert.match(html,/平倉佣金/);
 assert.doesNotMatch(html,/本機模擬成交|已實現損益 USD/);
});

test('stale pnl or missing broker fields never become a current zero',()=>{
 const stale=structuredClone(market);stale.account!.pnl_status='STALE';stale.account!.positions[0].net_pnl=null;
 const html=renderToStaticMarkup(createElement(BrokerAccountView,{market:stale,activity,tab:'positions'}));
 assert.match(html,/損益已過期/);assert.match(html,/—/);
 assert.doesNotMatch(html,/12.34/);
 const offline=renderToStaticMarkup(createElement(BrokerAccountView,{market:null,activity:null,tab:'positions',error:'讀取失敗'}));
 assert.match(offline,/未連線|等待/);assert.match(offline,/讀取失敗/);
});

test('order history separates unknown submissions, actual close deals and truncation',()=>{
 const html=renderToStaticMarkup(createElement(BrokerAccountView,{market,activity,tab:'history'}));
 assert.match(html,/回報待核對/);assert.match(html,/勿重送/);assert.match(html,/-4.25/);
 assert.match(html,/已實現毛損益/);assert.match(html,/30 天/);assert.match(html,/尚有更多/);
 assert.match(html,/下一頁/);
 const unknown=html.match(/<tr data-status="UNKNOWN">.*?<\/tr>/)?.[0];
 assert(unknown);assert.match(unknown,/回報待核對/);assert.doesNotMatch(unknown,/已成交/);
});

test('pending orders have an explicit pending label and no nonexistent trading buttons',()=>{
 const html=renderToStaticMarkup(createElement(BrokerAccountView,{market,activity,tab:'pending'}));
 assert.match(html,/3990/);assert.match(html,/待成交/);
 assert.doesNotMatch(html,/取消委託|平倉<\/button>/);
});

test('a rejected deal report is never labelled an entry fill',()=>{
 const rejected=structuredClone(activity);rejected.broker_deals.items[0].status='REJECTED';
 const html=renderToStaticMarkup(createElement(BrokerAccountView,{market,activity:rejected,tab:'history'}));
 assert.match(html,/未確認成交/);assert.doesNotMatch(html,/進場成交|平倉成交/);
});

test('small broker pnl keeps supplied precision rather than becoming zero',()=>{
 const precise=structuredClone(market);precise.account!.positions[0].net_pnl='0.004';
 precise.account!.net_unrealized_pnl='0.004';precise.account!.equity='10000.004';
 const html=renderToStaticMarkup(createElement(BrokerAccountView,{market:precise,activity,tab:'positions'}));
 assert.match(html,/0.004/);assert.match(html,/10000.004/);
});

test('submitted close is labelled as closing original position, not opening another buy',()=>{
 const closed=structuredClone(activity);closed.submissions.items[0]={...closed.submissions.items[0],intent:'CLOSE',position_id:'123',status:'FILLED'};
 const html=renderToStaticMarkup(createElement(BrokerAccountView,{market,activity:closed,tab:'history'}));
 assert.match(html,/<td>平倉<small>部位 123/);assert.match(html,/<td>原買進<\/td>/);
});
