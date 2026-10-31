import test from 'node:test';import assert from 'node:assert/strict';import {createElement} from 'react';import {renderToStaticMarkup} from 'react-dom/server';
import AssistantControl from '../src/AssistantControl';import {decodeModelSelection,requestModelOptions} from '../src/modelSettings';import {setupHint,isModelAnalysis} from '../src/assistantProvider';
test('Codex choice uses returned model/effort rather than Claude fields',()=>{
 const selection=decodeModelSelection(JSON.stringify({provider:'codex',codex_model:'model-a',codex_effort:'high'}));
 const status={provider:'codex',provider_label:'Codex',configured:true,enabled:true,model:'model-a',models:[{id:'model-a',label:'Model A',efforts:['low','high'],default_effort:'low'}]};
 assert.deepEqual(requestModelOptions(status,selection),{provider:'codex',codex_model:'model-a',codex_effort:'high'});
 const html=renderToStaticMarkup(createElement(AssistantControl,{settings:{status,selection,refresh:()=>{},update:()=>{},requestOptions:{}}}));
 assert.match(html,/aria-label="AI供應商"/);assert.match(html,/Model A/);assert.doesNotMatch(html,/Sonnet<\/option>/);
 assert.match(setupHint({...status,configured:false,reason:'authentication_required'}),/codex login/);
 assert.ok(isModelAnalysis('codex_market_analysis'));
});
