import {test} from 'node:test';import assert from 'node:assert/strict';import {createElement} from 'react';import {renderToStaticMarkup} from 'react-dom/server';
import CaseOperations,{CaseOperationsView,loadCaseOperations,type OperationDetails} from '../src/CaseOperations';
const data:OperationDetails={snapshot_id:'original',case_ref:'案例甲',as_of_utc:'2026-10-22T01:00:00Z',status:'AVAILABLE',representative:{side:'BUY',action:'FIRST',lot:'.1',profit:'20',entry:'4000',exit:'4002',currency:'USD'},provided_rows:2,displayed_rows:2,reported_total:3,coverage:'PARTIAL',truncated:true,limitations:['只顯示來源可見序列，並非完整帳戶。'],rows:[{index:1,side:'BUY',lot:'.1',entry:'4000',exit:'4002',profit:'20',currency:null,result:'WIN',role:'可見初始單',ordering_uncertain:true},{index:2,side:'BUY',lot:'.2',entry:'3999',exit:'4002',profit:'60',currency:'USD',result:'WIN',role:'加倉',ordering_uncertain:false}]};
test('visible operations preserve row currency and flag partial coverage without a group total',()=>{
 const html=renderToStaticMarkup(createElement(CaseOperationsView,{data}));
 for(const text of ['代表單筆進場','來源可見','2','3','尚未顯示完整記載筆數','順序未確認','幣別未載','USD','可見初始單','加倉'])assert.ok(html.includes(text),text);
 assert.doesNotMatch(html,/群組淨損益|合計.*80|20 USD/);
});
test('operations load only on expansion and never embed identifiers in visible markup',()=>{
 const html=renderToStaticMarkup(createElement(CaseOperations,{snapshotId:'PRIVATE_SNAPSHOT',caseRef:'案例甲'}));
 assert.match(html,/同群可見操作/);assert.doesNotMatch(html,/PRIVATE_SNAPSHOT|4000|<table|overflow/);
});
test('loading validates immutable snapshot identity and never substitutes another case',async()=>{
 const calls:unknown[]=[];const result=await loadCaseOperations('original','案例甲',async path=>{calls.push(path);return structuredClone(data);});
 assert.equal(result.case_ref,'案例甲');assert.match(String(calls[0]),/operations\?case_ref=/);
 await assert.rejects(loadCaseOperations('another','案例甲',async()=>structuredClone(data)),/快照/);
 await assert.rejects(loadCaseOperations('original','案例乙',async()=>structuredClone(data)),/案例/);
 await assert.rejects(loadCaseOperations('original','案例甲',async()=>({...data,rows:null})),/格式/);
});
