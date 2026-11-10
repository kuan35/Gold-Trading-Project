import test from 'node:test';
import assert from 'node:assert/strict';
import {createElement} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import AgentAnswer from '../src/experience/AgentAnswer';
import {AgentTopbar} from '../src/experience/AgentDesk';
import type {MarketReply} from '../src/LiveAssistant';

const reply={provider:'claude_market_analysis',model:'sonnet',llm_status:'ok',market_status:'CURRENT',as_of_utc:'2026-11-09T01:00:00Z',
 trade_advice:{action:'WAIT'},evidence:[],sections:[
  {title:'綜合建議',text:'優先做多，回踩支撐守住再進場，跌破就取消計畫。',fact_ids:['f5.levels'],source:'model'},
  {title:'歷史操作參照',text:'2023年10月3日交易員做多，次日平倉，原單價格報酬為+0.50%。',fact_ids:['history.trade1','history.case1'],source:'model'},
  {title:'詳細統計',text:'這裡才放完整配對與演算法門檻。',fact_ids:['advice.comparison'],source:'model'},
 ]} as unknown as MarketReply;

test('the primary answer includes the agent historical trade story without opening the detailed statistics',()=>{
 const html=renderToStaticMarkup(createElement(AgentAnswer,{reply,onChart:()=>{}}));
 assert.match(html,/優先做多/);assert.match(html,/2023年10月3日/);assert.match(html,/\+0\.50%/);
 assert.doesNotMatch(html,/這裡才放完整配對/);
});

test('an omitted historical story still exposes original trade facts alongside the finished agent answer',()=>{
 const r={...reply,sections:reply.sections.slice(0,1),evidence:[{id:'history.trade1',text:'',values:{
  hist1_opened_day:'2023年10月3日',hist1_closed_day:'2023年10月4日',hist1_side_state:'做多',
  hist1_entry:'1780',hist1_exit:'1789',hist1_price_return:'0.5056',hist1_result_state:'獲利',
 }}]};
 const html=renderToStaticMarkup(createElement(AgentAnswer,{reply:r,onChart:()=>{}}));
 assert.match(html,/2023年10月3日/);assert.match(html,/1780/);assert.match(html,/1789/);assert.match(html,/0\.5056%/);
 assert.doesNotMatch(html,/勝率|保證金ROI/);
});

test('the quote header describes which price a user can actually buy or sell at',()=>{
 const html=renderToStaticMarkup(createElement(AgentTopbar,{market:null,light:false,onTheme:()=>{}}));
 assert.match(html,/可賣出價/);assert.match(html,/可買進價/);assert.doesNotMatch(html,/>BID<|>ASK</);
});

test('the answer footer states the actual matching and simulation denominators without using displayed length',()=>{
 const r={...reply,case_comparison:{counts:{passed:7,displayed:0,eligible:100},cases:[]},
  trade_advice:{action:'WAIT',simulations:{count:1}}} as unknown as MarketReply;
 const html=renderToStaticMarkup(createElement(AgentAnswer,{reply:r,onChart:()=>{}}));
 assert.match(html,/相似案例：7 組/);assert.match(html,/多空試算參考 1 組/);
 assert.ok(html.indexOf('相似案例：7 組')>html.indexOf('原單價格報酬為'));
 assert.doesNotMatch(html,/相似案例：100 組/);
 const same={...r,case_comparison:{...r.case_comparison!,counts:{passed:1,displayed:0,eligible:100}}};
 const single=renderToStaticMarkup(createElement(AgentAnswer,{reply:same,onChart:()=>{}}));
 assert.match(single,/相似案例：1 組/);assert.doesNotMatch(single,/多空試算參考/);
});

test('unknown or invalid counts are not turned into a zero-match claim',()=>{
 const html=renderToStaticMarkup(createElement(AgentAnswer,{reply,onChart:()=>{}}));
 assert.doesNotMatch(html,/相似案例：0 組/);
});

test('pooled historical performance replaces a single original trade in the summary',()=>{
 const r={...reply,case_comparison:{counts:{passed:6},cases:[],performance:{status:'AVAILABLE',total:6,known_results:6,
  wins:3,losses:2,flat:1,unknown_results:0,win_rate_pct:'50.00',price_results_count:6,mean_price_return_pct:'16.6667',mean_move_per_oz:'16.6667',
  unknown_currency_results:0,pnl_by_currency:[{currency:'USD',count:6,mean_pnl:'16.67',mean_win:'43.33',mean_loss:'-15.00'}]}}} as unknown as MarketReply;
 const html=renderToStaticMarkup(createElement(AgentAnswer,{reply:r,onChart:()=>{}}));
 assert.match(html,/歷史案例整體表現/);assert.match(html,/50.00%/);assert.match(html,/16.6667%/);assert.match(html,/16.67 USD/);
 assert.doesNotMatch(html,/2023年10月3日/);
});
