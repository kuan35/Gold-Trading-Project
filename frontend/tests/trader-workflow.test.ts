import test from 'node:test';import assert from 'node:assert/strict';
import {createElement} from 'react';import {renderToStaticMarkup} from 'react-dom/server';
import AgentAnswer from '../src/experience/AgentAnswer';
import NoCaseReasons from '../src/NoCaseReasons';
import type {MarketReply} from '../src/LiveAssistant';
import {RiskNumbers} from '../src/TicketRiskPanel';

test('the question answer precedes a collapsed no-match explanation',()=>{
 const reply={provider:'program_live',market_status:'CURRENT',as_of_utc:'2026-11-04T00:00:00Z',sections:[{title:'五分鐘',text:'這是先回答的盤面重點',fact_ids:['f5.trend']}],evidence:[],case_comparison:{status:'NO_RULE_MATCH',label:'沒有符合案例',reason:'走勢差異較大',counts:{eligible:5000,passed:0,displayed:0},cases:[],rejections:[{key:'five_path',label:'路徑差距',count:4999}]}} as unknown as MarketReply;
 const html=renderToStaticMarkup(createElement(AgentAnswer,{reply,onChart:()=>{}}));
 assert.ok(html.indexOf('這是先回答的盤面重點')<html.indexOf('沒有符合案例'));
 assert.match(html,/<details[^>]*>[\s\S]*4999/);
 const compact=renderToStaticMarkup(createElement(NoCaseReasons,{comparison:reply.case_comparison!,compact:true}));
 assert.match(compact,/檢視未通過原因/);assert.doesNotMatch(compact,/<details[^>]*open/);
});

test('risk card separates equity risk and reward ratio from leveraged ROI, missing total stays unknown',()=>{
 const html=renderToStaticMarkup(createElement(RiskNumbers,{risk:{status:'UNKNOWN',reason:'有持倉未設停損',stop_loss_usd:'100.00',stop_equity_pct:'1.0000',reward_risk_ratio:'2.0000',existing_positions_risk_usd:null,pending_orders_risk_usd:'0.00',gold_total_risk_usd:null,gold_total_equity_pct:null,unprotected_positions:['p1'],unprotected_orders:[],scope:'黃金額外風險'}}));
 assert.match(html,/1.0000%/);assert.match(html,/1：2.0000/);assert.match(html,/無法完整估算/);assert.doesNotMatch(html,/合計[^<]*0.00/);
});
