import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createElement} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import DeskRouteFrame from '../src/DeskRouteFrame';
import LivePageGuide from '../src/LivePageGuide';
import type {DemoMarket} from '../src/demoMarket';

const render=(view:'assistant'|'live'|'replay',publicMode=false,busy=false)=>renderToStaticMarkup(createElement(DeskRouteFrame,{view,market:null,light:false,publicMode,busy,onNavigate:()=>{},onSection:()=>{},onToggleTheme:()=>{},children:createElement('main',null,'page content')}));
test('secondary pages expose the same navigation with the actual selected page',()=>{
 const html=render('live');
 assert.match(html,/aria-current="page"[^>]*>.*即時看盤/);
 assert.match(html,/歷史回放/);assert.match(html,/交易對話/);assert.match(html,/等待即時報價/);
 assert.doesNotMatch(html,/24H|2357\.62|已連線/);
});
test('public page shell keeps demo account capability unavailable',()=>{
 const html=render('replay',true);
 assert.match(html,/公開展示/);assert.match(html,/合成回放/);
 assert.doesNotMatch(html,/帳戶已連線|行情已連線|cTrader DEMO/);
});
test('locked replay work cannot navigate through a second unlocked navigation',()=>{
 const html=render('replay',false,true);
 assert.equal((html.match(/disabled=""/g)||[]).length,6);
});
test('assistant retains the route body container without duplicated navigation or header',()=>{
 const html=render('assistant');
 assert.match(html,/pd-route-body/);assert.match(html,/page content/);
 assert.doesNotMatch(html,/工作台頁面|pd-page-heading|pd-market/);
});
const guideProps={market:null,publicMode:false,side:'BUY' as const,method:'context_contract_v1' as const,onSide:()=>{},onMethod:()=>{},onAssistant:()=>{},onAccount:()=>{},onReplay:()=>{},onReplayCases:()=>{},onReplayOrder:()=>{},children:null};
test('live guide does not show stale equity or infer empty positions from a missing account',()=>{
 const empty=renderToStaticMarkup(createElement(LivePageGuide,guideProps));
 assert.match(empty,/等待連線/);assert.doesNotMatch(empty,/0／0|0\.00/);
 const market={connection_status:'CONNECTED',account:{status:'CURRENT',pnl_status:'STALE',balance:'100.00',equity:'12345.67',currency:'USD',positions:[],pending_orders:[]}} as unknown as DemoMarket;
 const html=renderToStaticMarkup(createElement(LivePageGuide,{...guideProps,market}));
 assert.match(html,/100\.00/);assert.doesNotMatch(html,/12345\.67/);
});
test('public live guide offers replay tools without a private demo order control',()=>{
 const html=renderToStaticMarkup(createElement(LivePageGuide,{...guideProps,publicMode:true}));
 assert.match(html,/查看回放案例/);assert.match(html,/使用模擬下單/);
 assert.doesNotMatch(html,/開啟交易對話與委託|已同步|案例檢索方法/);
});
