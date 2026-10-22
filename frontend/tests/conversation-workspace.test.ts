import {test} from 'node:test';import assert from 'node:assert/strict';import {createElement} from 'react';import {renderToStaticMarkup} from 'react-dom/server';
import ConversationWorkspace from '../src/ConversationWorkspace';import ConversationReply,{compactSections,compactReplySections} from '../src/ConversationReply';import type {MarketReply} from '../src/LiveAssistant';
test('local homepage presents one shared ticket and discussion without default candles or replay prices',()=>{
 const html=renderToStaticMarkup(createElement(ConversationWorkspace,{market:null,light:false,visible:true,onHistory:()=>{}}));
 for(const text of ['交易對話','準備中委託','檢查 DEMO 委託','啟用 Groq'])assert.ok(html.includes(text),text);
 assert.doesNotMatch(html,/chart-canvas|本機回放淨值|2927.75/);
 assert.match(html,/尚未選擇方向/);
});
test('compact answer preserves hourly background instead of two redundant short-term sections',()=>{
 const sections=[{title:'短線結構',text:'',fact_ids:['f5.trend']},{title:'短線動能',text:'',fact_ids:['f5.momentum']},{title:'一小時背景',text:'',fact_ids:['f1.trend']}];
 assert.deepEqual(compactSections(sections).map(s=>s.title),['短線結構','一小時背景']);
});
test('program answer summarizes selected timeframe facts instead of a long indicator wall',()=>{
 const reply={provider:'program_live',sections:[{title:'報價',text:'quote',fact_ids:['quote']},{title:'五分鐘',text:'long indicator wall',fact_ids:['f5.trend','f5.momentum']},{title:'一小時',text:'another indicator wall',fact_ids:['f1.trend','f1.momentum']}],evidence:[{id:'f5.trend',text:'五分鐘 {{bias}}',values:{bias:'偏空'}},{id:'f1.trend',text:'一小時 {{bias}}',values:{bias:'偏多'}}]} as unknown as MarketReply;
 assert.deepEqual(compactReplySections(reply).map(s=>s.text),['五分鐘 偏空','一小時 偏多']);
});
test('compact reply uses representative single outcome and preserves unknown currency',()=>{
 const reply={provider:'program',llm_status:'disabled',market_status:'CURRENT',as_of_utc:'2026-10-22T01:00:00Z',snapshot_id:'x',sections:[{title:'五分鐘',text:'下跌後回到區間。',fact_ids:[]}],evidence:[],case_comparison:{query_as_of_utc:1800000000,label:'有符合條件案例',reason:'通過規則',cases:[{ref:'案例甲',event:'區間內',tail_direction:'上行',similarities:['方向相同'],differences:['波動較大'],metrics:[],representative:{profit:'-14.50',currency:null,currency_stated:false,result:'LOSS',side:'BUY',lot:'.1',action:'FIRST'}}],counts:{eligible:4,passed:1,displayed:1},rejections:[],side:'BUY'}} as unknown as MarketReply;
 const html=renderToStaticMarkup(createElement(ConversationReply,{reply,onChart:()=>{}}));
 assert.match(html,/代表單筆原報表結果/);assert.match(html,/-14.50/);assert.match(html,/幣別未載/);assert.doesNotMatch(html,/全群損益|USD|PRIVATE_ID/);
});
