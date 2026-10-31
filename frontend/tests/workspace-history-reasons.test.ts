import test from 'node:test';import assert from 'node:assert/strict';import {createElement} from 'react';import {renderToStaticMarkup} from 'react-dom/server';
import {makeArchiveEntry,mergeArchive,renameConversation,deleteConversation,encodeArchive,decodeArchive} from '../src/deskConversations';
import NoCaseReasons,{noCaseReasons} from '../src/NoCaseReasons';
import type {CaseComparisonData} from '../src/CaseComparison';

test('custom thread title survives new turns and deletion of the last thread persists',()=>{
 const entry=makeArchiveEntry('one',[{question:'做多討論',answer:'回覆',at:'2026-10-31T00:00:00Z'}],1);
 const before=[entry],renamed=renameConversation(before,'one','我的黃金計畫');
 assert.equal(before[0].title,'做多討論');assert.equal(renamed[0].title,'我的黃金計畫');
 const updated=mergeArchive(renamed,makeArchiveEntry('one',[...entry.turns,{question:'改看一小時',answer:'討論',at:'2026-10-31T00:01:00Z'}],2));
 assert.equal(decodeArchive(encodeArchive(updated)).items[0].title,'我的黃金計畫');
 assert.deepEqual(decodeArchive(encodeArchive(deleteConversation(updated,'one'))).items,[]);
 assert.throws(()=>renameConversation(updated,'one','   '));
});

test('no-case reasons show primary exclusions and missing tick data above details',()=>{
 const c={status:'NO_RULE_MATCH',label:'無符合案例',reason:'有可比較案例但未通過',counts:{eligible:30,passed:0,displayed:0},cases:[],rejections:[
  {key:'five_path',label:'五分鐘走勢差距超過容忍',count:20},{key:'tick_volume_ratio',label:'tick活躍度差距超過2倍',count:5}]} as unknown as CaseComparisonData;
 const html=renderToStaticMarkup(createElement(NoCaseReasons,{comparison:c}));
 assert.match(html,/主要未通過原因/);assert.match(html,/五分鐘走勢/);assert.match(html,/tick活躍度/);assert.doesNotMatch(html,/<details/);
 const missing={...c,status:'INSUFFICIENT_DATA',tick_volume:{enabled:true,query_reason:'SOURCE_UNAVAILABLE'}};
 assert.ok(noCaseReasons(missing).some(s=>s.includes('來源')));
 assert.equal(renderToStaticMarkup(createElement(NoCaseReasons,{comparison:{...c,status:'PASSED'}})),'');
});
