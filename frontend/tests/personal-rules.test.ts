import test from 'node:test';
import assert from 'node:assert/strict';
import {parseRuleMessage,validateRules,evaluateRules,ruleText,changeRules} from '../src/personalRules';
import type {PersonalRule} from '../src/personalRules';
import {browserAPI} from '../src/demo';
import {renderToStaticMarkup} from 'react-dom/server';
import {createElement} from 'react';
import {RuleResults,RuleProposalCard} from '../src/PersonalRulesPanel';
const rule:PersonalRule={id:'r1',kind:'order_lot',value:'0.10',op:'gt',enabled:true,side:'ANY'};
test('parse settings before order intent; unsupported compound is not accepted',()=>{
 const result=parseRuleMessage('以後買進超過0.1手就提醒我',[]);
 assert.equal(result?.proposal?.rule?.kind,'order_lot');
 assert.equal(result?.proposal?.rule?.side,'BUY');
 assert.equal(parseRuleMessage('買進0.2手',[]),null);
 assert.equal(parseRuleMessage('手數超過0.1而且沒停損提醒我',[])?.proposal,undefined);
});
test('edit and pause identify saved rule; no immediate mutation',()=>{
 const result=parseRuleMessage('把第1條改成0.2手',[rule]);
 assert.equal(result?.proposal?.rule?.value,'0.2');assert.equal(rule.value,'0.10');
 assert.equal(parseRuleMessage('暫停第1條',[rule])?.proposal?.rule?.enabled,false);
 assert.equal(changeRules([rule],result!.proposal!)[0].value,'0.2');
});
test('precision boundary and missing values',()=>{
 const state={positions:[]} as any;
 const draft={side:'BUY',lot:'0.10',sl:null,risk:{after_lot:'.3',stop_loss_usd:null}} as any;
 assert.equal(evaluateRules([rule],state,draft).results[0].status,'clear');
 assert.equal(evaluateRules([{...rule,op:'gte'}],state,draft).results[0].status,'triggered');
 assert.equal(evaluateRules([rule],state,null).results[0].status,'unknown');
 assert.equal(evaluateRules([{...rule,kind:'stop_loss_usd',value:'100'}],state,draft).results[0].status,'unknown');
 assert.match(ruleText(rule),/0.10/);
});
test('invalid rule storage is rejected rather than silently discarded',()=>{
 for(const value of ['NaN','Infinity','0','-1'])assert.throws(()=>validateRules([{...rule,value}]));
 assert.throws(()=>validateRules([rule,rule]));
 assert.throws(()=>validateRules([{...rule,kind:'same_side_count',value:'1.5'}]));
});
test('ambiguous units, negation, multiple conditions and other periods need clarification',()=>{
 for(const text of ['單筆不超過0.1手提醒我','單筆超過0.1美元提醒我','單筆超過0.1手或總手數超過1手提醒我','15分鐘偏空就提醒我'])assert.equal(parseRuleMessage(text,[])?.proposal,undefined,text);
});
test('rules and reminders render actionable previews and honest unknown state',()=>{
 const preview=renderToStaticMarkup(createElement(RuleProposalCard,{proposal:{action:'save',rule},busy:false,onConfirm:()=>{},onCancel:()=>{}}));
 assert.match(preview,/確認儲存/);assert.match(preview,/此瀏覽器/);
 const check=evaluateRules([rule],{positions:[]},null);
 assert.match(renderToStaticMarkup(createElement(RuleResults,{check})),/無法判斷/);
});
test('Pages validates before draft, checks rules and rejects stale rule snapshot',async()=>{
 await browserAPI('/replay/reset',{});
 const draft=await browserAPI('/drafts',{side:'BUY',lot:'.2',personal_rules:[rule]}) as any;
 assert.equal(draft.personal_rules.results[0].status,'triggered');
 await assert.rejects(browserAPI(`/drafts/${draft.id}/confirm`,{revision:draft.revision,idempotency_key:'mismatch',personal_rules:[]}),/規則已更新/);
 const filled=await browserAPI(`/drafts/${draft.id}/confirm`,{revision:draft.revision,idempotency_key:'match',personal_rules:[rule]}) as any;
 assert.equal(filled.state.orders.length,1);
 const chat=await browserAPI('/chat',{message:'以後買進超過0.1手提醒我',personal_rules:[rule]}) as any;
 assert.equal(chat.draft,null);
});
