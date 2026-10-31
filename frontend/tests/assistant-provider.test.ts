import test from 'node:test';import assert from 'node:assert/strict';
import {isModelAnalysis,analysisLabel,setupHint} from '../src/assistantProvider';
import {compactReplySections} from '../src/ConversationReply';
import type {MarketReply} from '../src/LiveAssistant';
test('Claude replies use model sections instead of being mistaken for program fallback',()=>{
 const reply={provider:'claude_market_analysis',sections:[{title:'重點',text:'模型白話解讀',fact_ids:['f5.trend']},{title:'限制',text:'限',fact_ids:['limits']}]} as MarketReply;
 assert.equal(isModelAnalysis(reply.provider),true);assert.equal(analysisLabel(reply.provider),'Claude Code');
 assert.deepEqual(compactReplySections(reply).map(s=>s.text),['模型白話解讀']);
 assert.equal(analysisLabel('groq_market_analysis'),'Groq');assert.equal(analysisLabel('local_market_rules'),'程式解讀');
});
test('missing Claude login explains official login and never asks for tokens',()=>{
 const hint=setupHint({configured:false,enabled:false,provider:'claude_code',provider_label:'Claude Code',reason:'authentication_required',model:'sonnet',supports_vision:false});
 assert.match(hint,/claude auth login/);assert.doesNotMatch(hint,/token|API key/);
});
