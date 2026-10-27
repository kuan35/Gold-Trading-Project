import {test} from 'node:test';import assert from 'node:assert/strict';import {createElement} from 'react';import {renderToStaticMarkup} from 'react-dom/server';
import CaseOutcomePanel from '../src/CaseOutcomePanel';import DraftScenarioRisk from '../src/DraftScenarioRisk';
import type {OutcomeAnalysis} from '../src/caseOutcomes';
import ConversationReply,{compactReplySections} from '../src/ConversationReply';import type {MarketReply} from '../src/LiveAssistant';
const risk={status:'AVAILABLE',reason:'本筆',side:'BUY',lot:'.1',order_type:'MARKET',entry_price:'2000',quantity_oz:'10',stop_price:'1990',target_price:'2020',stop_loss_usd:'100.00',scope:'THIS_DRAFT_ONLY',conditional_on_fill:false};
const h={status:'AVAILABLE',minutes:60,change_pct:'.5',mae_pct:'1',mfe_pct:'2',reason:''};
const a={status:'AVAILABLE',input_revision:4,matched_cases:20,displayed_cases:1,draft_risk:risk,cases:[{ref:'案例甲',horizons:{'30':{...h,minutes:30},'60':h},scenarios:{'30':{status:'AVAILABLE',mae_loss_usd:'200.00',end_pnl_usd:'100.00',touch_label:'同根五分棒碰到停損與停利，先後未知',touch_state:'BOTH_SAME_BAR'},'60':{status:'AVAILABLE',mae_loss_usd:'200.00',end_pnl_usd:'100.00',touch_label:'同根五分棒碰到停損與停利，先後未知',touch_state:'BOTH_SAME_BAR'}}}]} as OutcomeAnalysis;
test('case outcomes shows fixed historical horizon, adverse exposure and never calls it a forecast',()=>{
 const html=renderToStaticMarkup(createElement(CaseOutcomePanel,{analysis:a,snapshotId:'frozen'}));
 for(const phrase of ['5 分鐘','30 分鐘','1 小時','途中最大逆向','200.00','先後未知','查看進場前與後續對照'])assert.ok(html.includes(phrase),phrase);
 assert.doesNotMatch(html,/chart-canvas|未來勝率|未來預測線/);
});
test('no matches keeps a draft risk panel and never invents an historical example',()=>{
 const empty={...a,cases:[],status:'NO_MATCH',matched_cases:0,displayed_cases:0};
 const html=renderToStaticMarkup(createElement(DraftScenarioRisk,{analysis:empty,currentRevision:4}));
 assert.match(html,/100.00/);assert.match(html,/本筆/);assert.doesNotMatch(html,/案例甲/);
 assert.equal(renderToStaticMarkup(createElement(CaseOutcomePanel,{analysis:empty,snapshotId:'s'})),'');
});
test('stale draft revision and unknown monetary values are explicit',()=>{
 let html=renderToStaticMarkup(createElement(DraftScenarioRisk,{analysis:a,currentRevision:5}));
 assert.match(html,/欄位已變更/);
 html=renderToStaticMarkup(createElement(DraftScenarioRisk,{analysis:{...a,draft_risk:{...a.draft_risk,stop_loss_usd:null}},currentRevision:4}));
 assert.match(html,/未設定停損/);assert.doesNotMatch(html,/停損.*0.00/);
});
test('missing history is displayed as unavailable instead of zero movement',()=>{
 const missing={...a,cases:[{...a.cases[0],horizons:{'30':{...h,status:'GAPPED_WINDOW',reason:'缺少完整棒',change_pct:null,mae_pct:null,mfe_pct:null},'60':{...h,status:'GAPPED_WINDOW',reason:'缺少完整棒',change_pct:null,mae_pct:null,mfe_pct:null}}}]} as OutcomeAnalysis;
 const html=renderToStaticMarkup(createElement(CaseOutcomePanel,{analysis:missing,snapshotId:'s'}));
 assert.match(html,/缺少完整棒/);assert.doesNotMatch(html,/0.00%/);
});
test('the main conversation actually exposes historical scenario and draft risk together',()=>{
 const reply={provider:'program',llm_status:'disabled',market_status:'CURRENT',as_of_utc:'2026-10-27T00:00:00Z',snapshot_id:'s',sections:[],evidence:[],outcome_analysis:a} as unknown as MarketReply;
 const html=renderToStaticMarkup(createElement(ConversationReply,{reply,onChart:()=>{},currentRevision:4}));
 assert.match(html,/歷史後續與情境損失/);assert.match(html,/本筆草稿風險/);
});
test('scenario questions keep the LLM historical interpretation in the primary answer',()=>{
 const reply={provider:'groq_market_analysis',sections:[
  {title:'歷史情境',text:'途中逆向不同於停損後損失。',fact_ids:['history.outcome']},
  {title:'本筆風險',text:'只是新增本筆。',fact_ids:['draft.risk']},
  {title:'盤面',text:'目前多空混合。',fact_ids:['f1.trend']}],evidence:[]} as unknown as MarketReply;
 assert.ok(compactReplySections(reply,'解釋後續情境和停損').some(s=>s.fact_ids.includes('history.outcome')));
});
