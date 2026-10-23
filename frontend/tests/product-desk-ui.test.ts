import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createElement} from 'react';import {renderToStaticMarkup} from 'react-dom/server';
import {trendSignals} from '../src/discussionPanels';
import {DeskMarketHeader} from '../src/DeskChrome';
import DeskAccountTray from '../src/DeskAccountTray';
import ConversationWorkspace from '../src/ConversationWorkspace';
import type {MarketReply} from '../src/LiveAssistant';import type {DemoMarket} from '../src/demoMarket';
const reply={market_status:'CURRENT',evidence:[{id:'f5.trend',values:{f5_bias:'短線偏多'}},{id:'f1.trend',values:{f1_bias:'短線偏空'}}]} as unknown as MarketReply;
test('discussion signals follow actual closed-bar facts and the selected side without manufactured scores',()=>{
 const buy=trendSignals(reply,'BUY');assert.equal(buy.support[0].period,'5m');assert.equal(buy.against[0].period,'1h');
 const sell=trendSignals(reply,'SELL');assert.equal(sell.support[0].period,'1h');
 assert.equal(trendSignals(reply,null).support.length,0);
 assert.equal(trendSignals({...reply,market_status:'UNAVAILABLE'},'BUY').support.length,0);
 assert.equal(trendSignals({...reply,evidence:[{id:'f5.trend',text:'',values:{f5_bias:'混合'}}]},'BUY').support.length,0);
});
test('market header keeps unavailable quotes honest and does not invent daily change or volume',()=>{
 const html=renderToStaticMarkup(createElement(DeskMarketHeader,{market:null,light:false,onToggleTheme:()=>{}}));
 assert.match(html,/XAUUSD/);assert.match(html,/未連線|等待/);assert.doesNotMatch(html,/2357|24H|89\.4|0\.53|NaN/);
});
test('bottom account tray distinguishes an unknown account from a verified empty account',()=>{
 const html=renderToStaticMarkup(createElement(DeskAccountTray,{market:null}));
 assert.match(html,/持倉/);assert.match(html,/等待.*帳戶|帳戶.*未連線/);assert.doesNotMatch(html,/目前沒有.*持倉|0\.00 USD/);
});
test('stale account profit is not presented as current profit',()=>{
 const market={connection_status:'CONNECTED',quote:{status:'CURRENT',bid:'4000',ask:'4001',age_seconds:0},account:{status:'CURRENT',pnl_status:'STALE',currency:'USD',positions:[{id:'p1',side:'BUY',lot:'0.10',entry:'3900',net_pnl:'999.99'}],pending_orders:[]}} as unknown as DemoMarket;
 const html=renderToStaticMarkup(createElement(DeskAccountTray,{market}));
 assert.match(html,/p1|3900/);assert.doesNotMatch(html,/999\.99/);
});

test('desk summary hides stale equity and hidden desks do not mount duplicate account panels',()=>{
 const market={connection_status:'CONNECTED',quote:{status:'CURRENT',age_seconds:0},account:{status:'CURRENT',pnl_status:'STALE',currency:'USD',equity:'12345.67',positions:[],pending_orders:[]}} as unknown as DemoMarket;
 const props={market,light:false,visible:true,onHistory:()=>{}};
 const html=renderToStaticMarkup(createElement(ConversationWorkspace,props));
 assert.doesNotMatch(html,/12345\.67/);
 const hidden=renderToStaticMarkup(createElement(ConversationWorkspace,{...props,visible:false}));
 assert.doesNotMatch(hidden,/pd-account-content|DEMO 持倉與紀錄/);
});
