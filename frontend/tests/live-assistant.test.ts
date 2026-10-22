import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createElement} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {LiveAssistantReply,type MarketReply} from '../src/LiveAssistant';

const reply:MarketReply={message:'盤面解讀',provider:'groq_market_analysis',llm_status:'ok',model:'test-model',source:'ctrader_demo_xauusd',market_status:'CURRENT',as_of_utc:'2026-10-22T01:00:01Z',quote_time_utc:'2026-10-22T01:00:00Z',
 sections:[{title:'五分鐘走勢',text:'收盤4100；短線整理。',fact_ids:['f5.trend']}],followups:['支撐壓力在哪？'],evidence:[{id:'f5.trend',text:'收盤{{close}}',values:{close:'4100'}},{id:'unused',text:'unused fact',values:{}}],draft:null};

test('live answer shows its native source, snapshot times, model, followups and used evidence',()=>{
 const html=renderToStaticMarkup(createElement(LiveAssistantReply,{reply,onFollowup:()=>{}}));
 for(const text of ['Groq 盤面解讀','cTrader DEMO','即時資料快照','分析快照','test-model','五分鐘走勢','收盤4100','查看數據依據','支撐壓力在哪？'])assert.ok(html.includes(text),text);
 assert.doesNotMatch(html,/unused fact|\{\{close\}\}/);
});

test('fallback is visibly a program answer; unavailable market has no followup actions',()=>{
 const r={...reply,provider:'local_market_rules',llm_status:'market_unavailable',market_status:'UNAVAILABLE',sections:[],evidence:[],message:'目前沒有有效報價',model:null,quote_time_utc:null};
 const html=renderToStaticMarkup(createElement(LiveAssistantReply,{reply:r,onFollowup:()=>{}}));
 assert.match(html,/程式盤面解讀/);assert.match(html,/目前沒有有效報價/);assert.match(html,/行情未就緒/);
 assert.doesNotMatch(html,/<button|Groq 盤面解讀|test-model/);
});

test('model titles and prose are rendered as escaped text',()=>{
 const html=renderToStaticMarkup(createElement(LiveAssistantReply,{reply:{...reply,sections:[{title:'<script>bad</script>',text:'<img src=x onerror=bad()>',fact_ids:[]}]}}));
 assert.doesNotMatch(html,/<script>|<img src=x/);assert.match(html,/&lt;script&gt;/);
});

test('partially repaired narrative identifies program substitution rather than pure model output',()=>{
 const html=renderToStaticMarkup(createElement(LiveAssistantReply,{reply:{...reply,llm_status:'partial_grounding',message:'部分模型段落由程式補充。\n\n內容',sections:[{title:'程式補充數據',text:'收盤4100',fact_ids:['f5.trend'],source:'program'}]}}));
 assert.match(html,/Groq＋程式盤面解讀/);assert.match(html,/部分模型段落由程式補充/);assert.match(html,/程式補充數據/);
});
