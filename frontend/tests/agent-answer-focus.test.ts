import test from 'node:test';import assert from 'node:assert/strict';
import {createElement} from 'react';import {renderToStaticMarkup} from 'react-dom/server';
import AgentAnswer from '../src/experience/AgentAnswer';import type {MarketReply} from '../src/LiveAssistant';
test('a repaired quote ledger does not displace the model answer or turn into a clipped heading',()=>{
 const reply:MarketReply={provider:'claude_market_analysis',llm_status:'partial_grounding',model:'sonnet',market_status:'CURRENT',as_of_utc:'2000-01-01T00:00:00Z',source:'synthetic',quote_time_utc:null,message:'synthetic',followups:[],draft:null,evidence:[],sections:[
  {title:'程式補充數據',text:'Numerical ledger',fact_ids:['quote'],source:'program'},
  {title:'直接回答',text:'Short-term pullback remains the main counter-signal.',fact_ids:['f5.trend'],source:'model'},
  {title:'背景',text:'Hourly background remains supportive.',fact_ids:['f1.trend'],source:'model'}]};
 const html=renderToStaticMarkup(createElement(AgentAnswer,{reply,onChart:()=>{}}));
 assert.match(html,/Short-term pullback remains/);assert.match(html,/Hourly background remains/);
 assert.doesNotMatch(html,/ag-headline|Numerical ledger/);
});
