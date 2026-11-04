import test from 'node:test';import assert from 'node:assert/strict';
import {historyDateInput,historyTimestamp,mergeHistoryBars,historyGaps} from '../src/historyBrowserModel';
test('Taiwan and UTC datetime input roundtrip without browser timezone dependency',()=>{
 const t=Date.UTC(2024,0,2,0,5)/1000;
 assert.equal(historyDateInput(t,'Taiwan'),'2024-01-02T08:05');assert.equal(historyTimestamp('2024-01-02T08:05','Taiwan'),t);
 assert.equal(historyTimestamp('2024-02-30T08:00','Taiwan'),null);assert.equal(historyTimestamp('2024-01-02T00:05','UTC'),t);
});
test('history merges deduplicate, sort and bound chart memory',()=>{
 const row=(time:number)=>({time,open:1,high:2,low:1,close:2});
 assert.deepEqual(mergeHistoryBars([row(2),row(3)],[row(1),row(2)],'before',3).map(b=>b.time),[1,2,3]);
 assert.deepEqual(mergeHistoryBars([row(1),row(2)],[row(3),row(4)],'after',3).map(b=>b.time),[2,3,4]);
});
test('gap report includes a gap spanning two loaded pages',()=>{
 const row=(time:number)=>({time,open:1,high:2,low:1,close:2,volume:1});
 const merged=mergeHistoryBars([row(300),row(600)],[row(1500),row(1800)],'after');
 assert.deepEqual(historyGaps(merged,'5m'),[{from_time:900,to_time:1500,seconds:600}]);
});
