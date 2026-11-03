import test from 'node:test';import assert from 'node:assert/strict';
import {createElement} from 'react';import {renderToStaticMarkup} from 'react-dom/server';
import ConversationWorkspace from '../src/ConversationWorkspace';
import AgentAnswer from '../src/experience/AgentAnswer';
import AgentDrawer from '../src/experience/AgentDrawer';
import type {MarketReply} from '../src/LiveAssistant';
test('peer homepage opens its order tab, settings panel and complete agent welcome',()=>{
 const html=renderToStaticMarkup(createElement(ConversationWorkspace,{market:null,light:false,visible:true,onHistory:()=>{}}));
 assert.match(html,/ag-center/);assert.match(html,/今天想怎麼交易黃金/);
 assert.match(html,/aria-selected="true"[^>]*>下單/);
 assert.match(html,/id="side-ticket-lot"/);assert.match(html,/檢查 DEMO 委託/);
 assert.match(html,/助手設定/);assert.match(html,/最近有哪些總經事件/);
 assert.doesNotMatch(html,/chart-canvas|11,902|滑動送出|gd-entered|Groq 白話/);
});
const reply={provider:'claude_market_analysis',model:'sonnet',llm_status:'ok',market_status:'STALE',as_of_utc:'2026-11-03T01:00:00Z',message:'報價過期，請更新',analysis_history_error:'本機保存失敗',sections:[{title:'盤面',text:'盤面原文',fact_ids:[]}],evidence:[],case_comparison:{status:'NO_RULE_MATCH',label:'沒有符合案例',reason:'五分鐘走勢差異過大',counts:{eligible:10,passed:0,displayed:0},cases:[],rejections:[]}} as unknown as MarketReply;
test('peer answer displays critical warnings and true provider before collapsed details',()=>{
 const html=renderToStaticMarkup(createElement(AgentAnswer,{reply,onChart:()=>{}}));
 for(const text of ['Claude Code','報價過期','本機保存失敗','沒有符合案例','五分鐘走勢差異過大'])assert.ok(html.includes(text),text);
 assert.doesNotMatch(html,/class="ag-detail"|勝率|Groq 解讀/);
});
test('program reply never claims the unused model name from the configured API',()=>{
 const html=renderToStaticMarkup(createElement(AgentAnswer,{reply:{...reply,provider:'program_live',model:'gpt-4.1-mini'},onChart:()=>{}}));
 assert.match(html,/程式解讀/);assert.doesNotMatch(html,/gpt-4.1-mini/);
});
test('matched summary preserves result currency and never manufactures similarity probability',()=>{
 const matched={...reply,market_status:'FROZEN',case_comparison:{...reply.case_comparison!,status:'PASSED',side:'BUY',cases:[{ref:'案例甲',event:'跌破後收回',tail_direction:'上行',similarities:['情境相同'],differences:['波動不同'],metrics:[],representative:{profit:'-12.30',currency:null,currency_stated:false,result:'LOSS',side:'BUY',action:'FIRST',lot:'0.1'}}]}};
 const html=renderToStaticMarkup(createElement(AgentAnswer,{reply:matched,onChart:()=>{}}));
 assert.match(html,/-12.30/);assert.match(html,/幣別未載/);assert.doesNotMatch(html,/USD|勝率|相似度.*%/);
});
test('closing drawer or selecting another tab retains the order slot in the component tree',()=>{
 for(const state of [{open:false,tab:'order' as const},{open:true,tab:'account' as const}]){
  const html=renderToStaticMarkup(createElement(AgentDrawer,{...state,onTab:()=>{},onClose:()=>{},light:false,market:null,order:createElement('div',{'data-review-id':'unchanged'},'原核對委託')}));
  assert.match(html,/data-review-id="unchanged"/);assert.match(html,/原核對委託/);
 }
});
