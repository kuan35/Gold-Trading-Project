import test from 'node:test';import assert from 'node:assert/strict';import {createElement} from 'react';import {renderToStaticMarkup} from 'react-dom/server';
import {MacroEvents,GoldInfluence} from '../src/MacroEvents';import {goldQuestionKind,requestsMacroContext,eventTimeLabel,eventProximity,type MacroSnapshot,type GoldRelation} from '../src/macroEventModel';
import ConversationWorkspace from '../src/ConversationWorkspace';
import ConversationReply from '../src/ConversationReply';import {archiveTurn} from '../src/conversationArchive';import type {MarketReply} from '../src/LiveAssistant';
const relation:GoldRelation={title:'通膨',mechanism:'透過利率與美元影響黃金',bullish:'若利率回落可能支持黃金',bearish:'若利率走高可能壓抑黃金',unknown:'尚未提供公布值與共識',sources:['https://www.gold.org/goldhub/']};
const macro:MacroSnapshot={status:'PARTIAL',snapshot_id:'macro',as_of_utc:'2026-11-01T00:00:00Z',coverage:'官方排程',sources:[{id:'bls',url:'https://www.bls.gov/schedule/',status:'UNAVAILABLE',fetched_at_utc:null,reason:'HTTP_403'}],news:[],consensus_status:'NOT_PROVIDED',actual_values_status:'NOT_FETCHED',events:[{id:'one',title:'CPI',topic:'CPI',date:'2026-11-10',scheduled_at_utc:null,timing_precision:'DATE_ONLY',status:'SCHEDULED',source_url:'https://www.bls.gov/schedule/',freshness:'CURRENT',fetched_at_utc:'2026-11-01T00:00:00Z',actual:null,consensus:null,previous:null,gold_relation:relation}]};
test('trading conversation starts without an unsolicited event panel',()=>{
 const html=renderToStaticMarkup(createElement(ConversationWorkspace,{market:null,light:false,visible:true,onHistory:()=>{}}));
 assert.match(html,/交易對話/);assert.doesNotMatch(html,/macro-bar|看多空關聯|正在查詢官方行事曆/);
});
test('market and order discussions add macro context only when asked',()=>{
 for(const q of ['分析目前黃金盤面','我想做多0.1手','附近支撐壓力在哪','更新目前盤面與案例'])assert.equal(requestsMacroContext(q),false,q);
 for(const q of ['CPI如何影響黃金','今天有什麼消息面影響','我想做多黃金，非農要注意什麼','下週FOMC何時','幫我看經濟行事曆'])assert.equal(requestsMacroContext(q),true,q);
});
test('every event explains both gold scenarios, missing results and source coverage',()=>{
 const html=renderToStaticMarkup(createElement(MacroEvents,{snapshot:macro}));
 for(const value of ['影響機制','可能偏多','可能偏空','尚未提供','部分來源','待確認','bls'])assert.ok(html.includes(value),value);
 assert.doesNotMatch(html,/預期為0|已降息|必漲|必跌/);
});
test('date-only and stale feeds never produce a fabricated precise countdown',()=>{
 const e=macro.events[0];assert.match(eventTimeLabel(e),/美東日期|時刻待確認/);assert.match(eventProximity(e,Date.parse(macro.as_of_utc)),/待確認/);
 assert.match(eventProximity({...e,scheduled_at_utc:'2026-11-01T00:10:00Z',freshness:'STALE'},Date.parse(macro.as_of_utc)),/快取|核對/);
});
test('gold questions route independently but explicit order instructions stay in the draft path',()=>{
 assert.equal(goldQuestionKind('CPI是什麼'),'knowledge');assert.equal(goldQuestionKind('今天有什麼重大經濟事件'),'calendar');
 assert.equal(goldQuestionKind('最近聯準會有何消息'),'news');assert.equal(goldQuestionKind('CPI前幫我買進0.1手'),null);assert.equal(goldQuestionKind('我想做多黃金，非農要注意什麼'),null);
 assert.equal(goldQuestionKind('今天聯準會消息如何影響黃金？'),'news');assert.equal(goldQuestionKind('什麼是停損'),'knowledge');
});
test('knowledge render does not show missing quote error and archive retains both event scenarios',()=>{
 const reply:MarketReply={message:'知識',provider:'local_gold_knowledge',model:null,llm_status:'disabled',source:'official',market_status:'INFORMATION',as_of_utc:macro.as_of_utc,quote_time_utc:null,draft:null,followups:[],evidence:[],analysis_mode:'gold_knowledge',sections:[{title:'黃金知識',text:'知識解釋',fact_ids:[]},{title:'黃金關聯',text:'另一段',fact_ids:[]}],macro_context:macro,gold_relation:relation};
 const html=renderToStaticMarkup(createElement(ConversationReply,{reply,onChart:()=>{}}));assert.doesNotMatch(html,/行情尚未就緒/);assert.match(html,/可能偏空/);
 const stored=archiveTurn({question:'CPI',reply});assert.match(stored.answer,/可能偏多/);assert.match(stored.answer,/可能偏空/);assert.match(stored.answer,/www.bls.gov/);
 const unsafe=renderToStaticMarkup(createElement(GoldInfluence,{relation:{...relation,sources:['javascript:alert(1)']}}));assert.doesNotMatch(unsafe,/href="javascript/);
});
