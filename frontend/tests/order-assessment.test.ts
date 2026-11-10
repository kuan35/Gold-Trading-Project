import test from 'node:test';import assert from 'node:assert/strict';
import {createElement} from 'react';import {renderToStaticMarkup} from 'react-dom/server';
import ConversationOrderReview from '../src/ConversationOrderReview';
const draft:any={id:'same-draft',revision:1,side:'BUY',lot:'0.1',order_type:'LIMIT',price:'4000',sl:'3990',tp:'4020',expires_at_utc:'2999-01-01T00:00:00Z',analysis_snapshot_id:'same-snapshot',analysis_as_of_utc:'2000-01-01T00:00:00Z',analysis_reply:{trade_advice:{headline:'舊程式建議等待',reason:'程式理由'}},risk:{before_lot:'0',after_lot:'0.1',stop_loss_usd:'100',scenarios:[],warnings:[]}};
const reply:any={provider:'claude_market_analysis',model:'sonnet',llm_status:'ok',snapshot_id:'same-snapshot',as_of_utc:'2000-01-01T00:00:00Z',analysis_mode:'draft_snapshot',market_status:'FROZEN',sections:[{title:'這筆委託評估',text:'做多草稿配合回升；歷史平均正報酬支持此想法，但回檔仍須控管。',fact_ids:['f5.trend','history.aggregate','history.case1'],source:'model'}]};
const props={draft,checkedRevision:1,currentRevision:1,onClear:()=>{},onLock:()=>{},onHistory:()=>{}};
test('confirmation review uses the same agent summary rather than an independent program verdict',()=>{
 const html=renderToStaticMarkup(createElement(ConversationOrderReview,{...props,assessment:{state:'ready',reply}}));
 assert.match(html,/歷史平均正報酬支持此想法/);assert.doesNotMatch(html,/舊程式建議等待|程式理由/);
});
test('pending or failed agent assessment does not silently fall back to a conflicting recommendation',()=>{
 for(const assessment of [{state:'pending' as const},{state:'error' as const,error:'助手資料核對未完成'}]){
  const html=renderToStaticMarkup(createElement(ConversationOrderReview,{...props,assessment}));
  assert.match(html,/助手/);assert.doesNotMatch(html,/舊程式建議等待/);
 }
 const html=renderToStaticMarkup(createElement(ConversationOrderReview,{...props,assessment:{state:'ready',reply:{...reply,snapshot_id:'another'}}}));
 assert.doesNotMatch(html,/歷史平均正報酬支持此想法/);
});

test('missing model-history relationship is stated in the review rather than presented as complete',()=>{
 const html=renderToStaticMarkup(createElement(ConversationOrderReview,{...props,assessment:{state:'ready',reply:{...reply,summary_evidence_state:'INCOMPLETE_HISTORY'}}}));
 assert.match(html,/助手尚未完整說明歷史案例/);assert.doesNotMatch(html,/舊程式建議等待/);
});
