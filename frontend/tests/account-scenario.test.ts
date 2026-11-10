import test from 'node:test';import assert from 'node:assert/strict';
import {createElement} from 'react';import {renderToStaticMarkup} from 'react-dom/server';
import {AccountZeroEstimate,PositionReturns} from '../src/AccountScenario';
test('zero-equity estimate is clearly conditional and never labelled a stop-out price',()=>{
 const estimate={status:'AVAILABLE',reason:null,zero_bid_price:'3800.20',direction:'DOWN' as const,basis:'固定部位與價差情境'};
 const html=renderToStaticMarkup(createElement(AccountZeroEstimate,{value:estimate}));
 assert.match(html,/跌至 3800.20/);assert.match(html,/淨值歸零/);assert.match(html,/不是強平價/);
 const stale=renderToStaticMarkup(createElement(AccountZeroEstimate,{value:estimate,pending:true}));assert.match(stale,/3800.20/);assert.match(stale,/aria-busy="true"/);
 const missing=renderToStaticMarkup(createElement(AccountZeroEstimate,{value:{status:'UNAVAILABLE',reason:'不是USD帳戶',zero_bid_price:null,direction:null,basis:''}}));
 assert.match(missing,/不是USD帳戶/);assert.doesNotMatch(missing,/0.00/);
});
test('position price and estimated margin returns use distinct labels and preserve unknowns',()=>{
 const html=renderToStaticMarkup(createElement(PositionReturns,{value:{price_return_pct:'-0.2500',estimated_margin_roi_pct:'-49.5000'}}));
 assert.match(html,/價格報酬率 -0.2500%/);assert.match(html,/預估保證金報酬率 -49.5000%/);
 const missing=renderToStaticMarkup(createElement(PositionReturns,{value:{price_return_pct:null,estimated_margin_roi_pct:null}}));
 assert.match(missing,/報酬率待更新/);assert.doesNotMatch(missing,/0%/);
});
test('actual broker-margin return is the primary holding result and price return is only detail',()=>{
 const html=renderToStaticMarkup(createElement(PositionReturns,{value:{price_return_pct:'0.2500',margin_roi_pct:'40.0000',margin_return_source:'BROKER_POSITION',used_margin:'100',return_currency:'USD'}}));
 assert.match(html,/<strong[^>]*>持倉報酬率 \+40.0000%<\/strong>/);
 assert.match(html,/<details><summary>報酬率依據<\/summary>.*價格報酬率 \+0.2500%/);
 assert.doesNotMatch(html,/預估保證金報酬率/);
 const zero=renderToStaticMarkup(createElement(PositionReturns,{value:{price_return_pct:'0.1',margin_roi_pct:null,estimated_margin_roi_pct:'20',margin_return_source:'UNAVAILABLE'}}));
 assert.match(zero,/持倉報酬率待更新/);assert.doesNotMatch(zero,/\+20.0000%/);
});
