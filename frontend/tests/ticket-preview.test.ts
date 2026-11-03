import test from 'node:test';import assert from 'node:assert/strict';
import {createElement} from 'react';import {renderToStaticMarkup} from 'react-dom/server';
import {TicketLevel} from '../src/TicketPreview';
test('SL/TP display keeps signed USD and price return, never labels it margin ROI',()=>{
 const html=renderToStaticMarkup(createElement(TicketLevel,{level:{status:'AVAILABLE',reason:null,pnl_usd:'-500.00',price_return_pct:'-0.2500'}}));
 assert.match(html,/-500.00 USD/);assert.match(html,/-0.2500%/);assert.match(html,/價格報酬率/);assert.doesNotMatch(html,/保證金報酬率/);
 const invalid=renderToStaticMarkup(createElement(TicketLevel,{level:{status:'INVALID_SIDE',reason:'停損方向錯誤',pnl_usd:null,price_return_pct:null}}));
 assert.match(invalid,/停損方向錯誤/);assert.doesNotMatch(invalid,/0.00/);
});
