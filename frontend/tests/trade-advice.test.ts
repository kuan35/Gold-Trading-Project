import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createElement} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import AgentAnswer from '../src/experience/AgentAnswer';
import {archiveTurn} from '../src/conversationArchive';
import type {MarketReply} from '../src/LiveAssistant';
import {adviceMode, riskBudgetFields} from '../src/tradeAdvice';

const reply: MarketReply = {
 message:'原有盤面分析', provider:'program', llm_status:'disabled', model:null, source:'ctrader_demo_xauusd',
 market_status:'CURRENT', as_of_utc:'2026-11-05T01:00:00Z', quote_time_utc:null, draft:null,
 sections:[{title:'盤面分析',text:'既有盤面分析',fact_ids:[]}], followups:[], evidence:[],
 trade_advice:{
  action:'ADJUST', side:'BUY', headline:'先調整手數', reason:'停損損失超過設定預算。',
  signal:'跌破後收回', as_of:1793840400,
  simulations:{count:12,BUY:{median_pct:'0.024',positive:8,better:8,stress_median_pct:'0.012'},SELL:{median_pct:'-0.031',positive:3,better:4,stress_median_pct:'-0.048'}},
  original:{BUY:{count:8,median_pct:'0.016',positive:5,negative:3},SELL:{count:0,median_pct:null,positive:0,negative:0}},
  costs:{baseline_usd_per_oz:'0.18',stress_usd_per_oz:'0.30'},
  protection:{status:'AVAILABLE',entry:'4000.00',stop:'3990.00',target:'4020.00',reward_risk_ratio:'2.00',
   stop_basis:'近期低點下方',target_basis:'原區間上緣',reason:null,entry_basis:'草稿限價',conditional:true},
  draft:{stop_loss_usd:'42.00',equity_pct:'0.7',budget_usd:'20.00',suggested_lot:'0.02',scenario:{stop:3,target:5,ambiguous:2,expired:1,unknown:1}},
 },
};

test('explicit decision questions and the workspace refresh request trade advice',()=>{
 assert.equal(adviceMode('現在該做多還是做空？'),'COMPARE');
 assert.equal(adviceMode('現在該買還是賣？'),'COMPARE');
 assert.equal(adviceMode('更新目前盤面與案例'),'COMPARE');
 assert.equal(adviceMode('我想做多，現在有哪些支持與相反訊號？','BUY'),'SIDE');
 assert.equal(adviceMode('如果做空，有類似案例嗎？','SELL'),undefined);
 assert.equal(adviceMode('如果做空會發生什麼事？','SELL'),'SIDE');
 assert.equal(adviceMode('解釋一小時為何偏多，五分鐘卻偏空','BUY'),undefined);
 assert.equal(adviceMode('現在適合做空嗎？','SELL'),'SIDE');
 assert.equal(adviceMode('現在適合做空嗎？'),undefined);
});

test('only a valid user-entered budget is sent and one unit is selected',()=>{
 assert.deepEqual(riskBudgetFields({mode:'usd',value:' 20.50 '}),{risk_usd:'20.50'});
 assert.deepEqual(riskBudgetFields({mode:'pct',value:'0.5'}),{equity_pct:'0.5'});
 for(const value of ['','-1','0','Infinity','100.01'])assert.deepEqual(riskBudgetFields({mode:'pct',value}),{});
});

test('conversation shows the actionable headline first and distinguishes paired and original denominators',()=>{
 const html=renderToStaticMarkup(createElement(AgentAnswer,{reply,onChart:()=>{}}));
 assert.ok(html.indexOf('先調整手數')<html.indexOf('既有盤面分析'));
 for(const label of ['同盤面 30 分鐘','交易員原單','8／12 組','5／8 組','42.00 USD','0.7%','0.02 手','順序未知 2 組',
  '停損停利條件式參考','建議停損 3990.00','建議停利 4020.00','草稿限價'])assert.ok(html.includes(label),label);
 assert.doesNotMatch(html,/0\/0|>0%/);
 const archived=archiveTurn({question:'現在可以做多嗎',reply});
 assert.ok(archived.answer.indexOf('先調整手數')<archived.answer.indexOf('既有盤面分析'));
 assert.match(archived.answer,/8／12 組/);
 assert.match(archived.answer,/建議停利 4020.00/);
});
