import test from 'node:test';import assert from 'node:assert/strict';import React from 'react';import {renderToStaticMarkup} from 'react-dom/server';
import AssistantControl from '../src/AssistantControl';
import {decodeModelSelection,selectionLabel,requestModelOptions} from '../src/modelSettings';

test('model controls show selectors and no enable checkbox',()=>{
 const selection={model:'opus',effort:'high'} as const;
 const html=renderToStaticMarkup(React.createElement(AssistantControl,{settings:{selection,status:{provider:'claude_code',provider_label:'Claude Code',configured:true,enabled:true,model:'sonnet',supports_vision:false},update:()=>{},refresh:()=>{},requestOptions:selection},busy:false}));
 assert.doesNotMatch(html,/type="checkbox"/);assert.match(html,/aria-label="模型"/);assert.match(html,/aria-label="思考程度"/);
 assert.match(html,/<option value="opus" selected="">/);assert.match(html,/<option value="high" selected="">/);
});
test('invalid saved selections reset to a bounded default',()=>{
 assert.deepEqual(decodeModelSelection(null),{model:'sonnet',effort:'medium'});
 assert.deepEqual(decodeModelSelection('{"model":"shell","effort":"ultracode"}'),{model:'sonnet',effort:'medium'});
 assert.deepEqual(decodeModelSelection('{"model":"haiku","effort":"max"}'),{model:'haiku',effort:'max'});
 assert.equal(selectionLabel('opus','high'),'Opus · 思考設定：深入');
});
test('unknown or Groq provider never receives Claude aliases during status loading or failure',()=>{
 const s={model:'opus',effort:'max'} as const;
 assert.deepEqual(requestModelOptions(null,s),{});
 assert.deepEqual(requestModelOptions({provider:'openai_compatible',configured:true,enabled:true,model:'groq'},s),{});
 assert.deepEqual(requestModelOptions({provider:'claude_code',configured:true,enabled:true,model:'sonnet'},s),s);
});
test('selectors wait for provider identity instead of displaying an actionable Claude choice',()=>{
 const html=renderToStaticMarkup(React.createElement(AssistantControl,{settings:{selection:{model:'opus',effort:'max'},status:null,update:()=>{},refresh:()=>{},requestOptions:{}}}));
 const select=html.match(/<select[^>]*aria-label="模型"[^>]*>/)?.[0]??'';
 assert.match(select,/disabled=""/);assert.match(html,/讀取中/);
});
