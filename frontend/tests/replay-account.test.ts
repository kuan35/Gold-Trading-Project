import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createElement} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {DemoEngine} from '../src/demo';
import ReplayAccountSummary from '../src/ReplayAccountSummary';

test('assistant replay summary shows spread loss immediately and has position/history routes',()=>{
 const engine=new DemoEngine();const draft=engine.draft('BUY','.1',null,null);
 engine.confirm(draft.id,draft.revision,'test');
 const html=renderToStaticMarkup(createElement(ReplayAccountSummary,{state:engine.state(),onPositions:()=>{},onHistory:()=>{},onClose:()=>{}}));
 assert.match(html,/-3.00/);assert.match(html,/回放浮動損益/);
 assert.match(html,/查看持倉/);assert.match(html,/下單與成交紀錄/);
 assert.match(html,/隨回放推進/);assert.doesNotMatch(html,/券商已成交/);
 assert.match(html,/aria-label="平倉本機部位/);
});

test('replay empty state does not invent a holding or hide transaction history',()=>{
 const html=renderToStaticMarkup(createElement(ReplayAccountSummary,{state:new DemoEngine().state(),onPositions:()=>{},onHistory:()=>{}}));
 assert.match(html,/目前沒有本機回放持倉/);assert.match(html,/下單與成交紀錄/);
});
