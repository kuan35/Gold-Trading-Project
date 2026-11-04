import test from 'node:test';import assert from 'node:assert/strict';import {createElement} from 'react';import {renderToStaticMarkup} from 'react-dom/server';
import ConversationWorkspace from '../src/ConversationWorkspace';
import TicketCheckAction from '../src/TicketCheckAction';
import SharedTicket from '../src/SharedTicket';import {emptyInput} from '../src/conversationState';
test('inline ticket exposes its own explicit review action without using chat send or immediate order submission',()=>{
 const html=renderToStaticMarkup(createElement(ConversationWorkspace,{market:null,light:false,visible:true,onHistory:()=>{}}));
 const inline=html.split('class="cw-inline"')[1]?.split('class="ag-chips"')[0]??'';
 assert.match(inline,/>檢查 DEMO 委託<\/button>/);assert.match(inline,/type="button"/);assert.match(inline,/待填：方向、單型、手數/);
 assert.doesNotMatch(inline,/確認送出 DEMO 委託|type="submit"/);
});
test('unset order type is explained next to the market and limit controls',()=>{
 const html=renderToStaticMarkup(createElement(SharedTicket,{id:'chat',value:{...emptyInput(),side:'BUY',lot:'0.30',sl:'90',tp:'110'},onPatch:()=>{}}));
 assert.match(html,/尚未選擇市價或限價/);assert.doesNotMatch(html,/aria-pressed="true">市價|aria-pressed="true">限價/);
});

test('review action preserves connection, checking and unresolved submission locks',()=>{
 for(const state of [{ready:false,checking:false,locked:false},{ready:true,checking:true,locked:false},{ready:true,checking:false,locked:true}]){
  let calls=0;const html=renderToStaticMarkup(createElement(TicketCheckAction,{id:'inline-action',...state,missing:[],onCheck:()=>{calls++;}}));
  assert.match(html,/<button[^>]*type="button"[^>]*disabled/);assert.equal(calls,0);assert.doesNotMatch(html,/確認送出 DEMO 委託/);
 }
});
test('ready fields expose review step, associated feedback and local error without requiring chat text',()=>{
 let calls=0;const html=renderToStaticMarkup(createElement(TicketCheckAction,{id:'inline-action',ready:true,checking:false,locked:false,missing:[],error:'停損位置不符',onCheck:()=>{calls++;}}));
 assert.match(html,/aria-describedby="inline-action-hint"/);assert.doesNotMatch(html,/<button[^>]*disabled/);
 assert.match(html,/檢查後核對風險，再由你確認送出/);assert.match(html,/role="alert"[^>]*>停損位置不符/);assert.equal(calls,0);
});
test('missing order type stays actionable for validation and is not silently set to market',()=>{
 const html=renderToStaticMarkup(createElement(TicketCheckAction,{id:'inline-action',ready:true,checking:false,locked:false,missing:['單型'],onCheck:()=>{}}));
 assert.match(html,/待填：單型/);assert.doesNotMatch(html,/<button[^>]*disabled/);
});
