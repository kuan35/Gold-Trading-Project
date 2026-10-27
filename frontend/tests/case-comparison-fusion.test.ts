import {test} from 'node:test';import assert from 'node:assert/strict';
import {createElement} from 'react';import {renderToStaticMarkup} from 'react-dom/server';
import CaseComparisonCharts from '../src/CaseComparisonCharts';
import {historicalDisplay,matchingOutcome} from '../src/caseComparisonData';
const candle=(time:number)=>({time,open:100,high:102,low:99,close:101});

test('future is appended only to historical bars, at actual times, with a clear boundary',()=>{
 const before=[candle(0),candle(300)];const future=[candle(900)];
 const result=historicalDisplay(before,{status:'AVAILABLE',anchor_time:900,bars:future});
 assert.deepEqual(result.bars.map(b=>b.time),[0,300,900]);
 assert.equal(result.markers[0].time,900);assert.match(result.markers[0].text,/後續/);
 assert.equal(result.futureCount,1);assert.deepEqual(before.map(b=>b.time),[0,300]);
 assert.equal(historicalDisplay(before,{status:'NOT_YET_KNOWN',bars:future}).futureCount,0);
 assert.equal(historicalDisplay(before,{status:'AVAILABLE',anchor_time:300,bars:future}).futureCount,0);
});

test('response identity rejects any other snapshot, case or horizon',()=>{
 const response={snapshot_id:'s',case_ref:'案例甲',history:{minutes:5}};
 assert.equal(matchingOutcome(response,'s','案例甲',5),true);
 assert.equal(matchingOutcome(response,'old','案例甲',5),false);
 assert.equal(matchingOutcome(response,'s','案例乙',5),false);
 assert.equal(matchingOutcome(response,'s','案例甲',30),false);
});

test('one comparison offers one shared case selector, 5/30/60 horizons and both timeframes',()=>{
 const data={snapshot_id:'s',query_as_of_utc:10000,query:{'5m':[candle(300)],'1h':[candle(0)]},cases:[
  {ref:'案例甲',as_of_utc:600,'5m':[candle(300)],'1h':[candle(0)]},
  {ref:'案例乙',as_of_utc:900,'5m':[candle(600)],'1h':[candle(0)]}]};
 const html=renderToStaticMarkup(createElement(CaseComparisonCharts,{data,light:false,initialCaseRef:'案例乙',initialMinutes:5}));
 for(const phrase of ['5 分鐘','30 分鐘','1 小時','五分 60 棒','一小時 20 棒','歷史後續','只顯示當時已收棒'])assert.ok(html.includes(phrase),phrase);
 assert.equal((html.match(/<select/g)||[]).length,1);
 assert.match(html,/<option value="案例乙" selected="">/);
 assert.doesNotMatch(html,/預測線|查詢後續實際/);
});
