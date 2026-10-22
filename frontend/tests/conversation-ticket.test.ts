import {test} from 'node:test';import assert from 'node:assert/strict';import {createElement} from 'react';import {renderToStaticMarkup} from 'react-dom/server';
import SharedTicket from '../src/SharedTicket';import {emptyInput} from '../src/conversationState';
test('controlled ticket starts unset and never submits by Enter',()=>{
 const html=renderToStaticMarkup(createElement(SharedTicket,{value:emptyInput(),onPatch:()=>{},id:'side'}));
 assert.match(html,/尚未選擇方向/);assert.match(html,/未設定/);assert.doesNotMatch(html,/<form|type="submit"|value="0.10"|aria-pressed="true"/);
});
test('two ticket instances reflect the exact same draft including limit and optional protection',()=>{
 const value={...emptyInput(),side:'SELL' as const,order_type:'LIMIT' as const,lot:'0.20',limit_price:'4400',sl:'4450'};
 for(const id of ['side','inline']){
  const html=renderToStaticMarkup(createElement(SharedTicket,{value,onPatch:()=>{},id}));
  for(const v of ['0.20','4400','4450','限價'])assert.ok(html.includes(v));
  assert.ok(html.includes(id+'-lot'));
 }
});
