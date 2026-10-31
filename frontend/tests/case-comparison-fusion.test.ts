import {test} from 'node:test';import assert from 'node:assert/strict';
import {createElement} from 'react';import {renderToStaticMarkup} from 'react-dom/server';
import CaseComparisonCharts from '../src/CaseComparisonCharts';
import {historicalDisplay,matchingOutcome} from '../src/caseComparisonData';
import type {Marker} from '../src/types';
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
 assert.equal((html.match(/<select aria-label="歷史案例"/g)||[]).length,1);
 assert.match(html,/<option value="案例乙" selected="">/);
 assert.match(html,/<button[^>]*aria-pressed="true"[^>]*>後續 5 分鐘<\/button>/);
 assert.doesNotMatch(html,/預測線|查詢後續實際/);
});

test('entry-only snapshots do not offer an exit jump or invent an exit marker',()=>{
 const data={snapshot_id:'entry-only',query_as_of_utc:10000,query:{'5m':[candle(300)],'1h':[candle(0)]},cases:[{
  ref:'案例甲',as_of_utc:600,'5m':[candle(300)],'1h':[candle(0)],execution:{status:'AVAILABLE',reason:'參考',bars:[candle(600)],close_bars:[],markers:[
   {time:600,position:'belowBar',color:'green',shape:'arrowUp',text:'進場參考',action:'ENTRY'} as Marker]}
 }]};
 const html=renderToStaticMarkup(createElement(CaseComparisonCharts,{data,light:false}));
 assert.match(html,/<button[^>]*disabled=""[^>]*>看出場<\/button>/);
 assert.doesNotMatch(html,/<button[^>]*disabled=""[^>]*>看進場<\/button>/);
});

test('historical entry and distant exit share one chart with focus controls by default',()=>{
 const data={snapshot_id:'s',query_as_of_utc:200000,query:{'5m':[candle(300)],'1h':[candle(0)]},cases:[{
  ref:'案例甲',as_of_utc:600,'5m':[candle(300)],'1h':[candle(0)],
  execution:{status:'AVAILABLE',reason:'參考',bars:[candle(600)],close_bars:[candle(100200)],markers:[
   {time:600,position:'belowBar',color:'green',shape:'arrowUp',text:'進場參考',action:'ENTRY'} as Marker,
   {time:100200,position:'aboveBar',color:'red',shape:'arrowDown',text:'平倉參考',action:'CLOSE'} as Marker]}
 }]};
 const html=renderToStaticMarkup(createElement(CaseComparisonCharts,{data,light:false}));
 assert.match(html,/<button[^>]*aria-pressed="true"[^>]*>原單進出場<\/button>/);
 for(const label of ['看進場','看出場','完整對照','中間時段未展開'])assert.ok(html.includes(label),label);
 assert.equal((html.match(/aria-label="案例甲五分K/g)||[]).length,1);
 assert.doesNotMatch(html,/與進場圖分開|出場附近五分K|顯示原單進場與出場/);
});

test('missing execution bars keep the fixed follow-up and explain unavailable exit',()=>{
 const data={snapshot_id:'s',query_as_of_utc:10000,query:{'5m':[candle(300)],'1h':[candle(0)]},cases:[{
  ref:'案例甲',as_of_utc:600,'5m':[candle(300)],'1h':[candle(0)],
  execution:{status:'UNAVAILABLE',reason:'平倉參考棒缺漏',bars:[],close_bars:[],markers:[]}
 }]};
 const html=renderToStaticMarkup(createElement(CaseComparisonCharts,{data,light:false}));
 assert.match(html,/五分 60 棒＋歷史後續/);
 assert.match(html,/平倉參考棒缺漏/);
 assert.doesNotMatch(html,/原單平倉附近/);
 assert.match(html,/<button[^>]*disabled=""[^>]*>看出場<\/button>/);
});

test('price return stays inside each historical chart without hovering',()=>{
 const data={snapshot_id:'s',query_as_of_utc:200000,query:{'5m':[candle(300)],'1h':[candle(0)]},cases:[{
  ref:'案例甲',as_of_utc:600,'5m':[candle(300)],'1h':[candle(0)],execution:{status:'AVAILABLE',reason:'參考',bars:[candle(600)],close_bars:[candle(100200)],markers:[],
   result:{status:'AVAILABLE',entry_price:'2000',exit_price:'2010',move_per_oz:'10',price_return_pct:'0.5',margin_roi_pct:null,reason:'before fees'}}
 }]};
 const html=renderToStaticMarkup(createElement(CaseComparisonCharts,{data,light:false}));
 assert.equal((html.match(/class="case-return-summary"/g)||[]).length,1);
 assert.equal((html.match(/class="chart-annotation"/g)||[]).length,1);
 assert.match(html,/<div class="chart-annotation"[^>]*><span class="case-return-summary">/);
 assert.doesNotMatch(html,/<span class="case-return-summary">[^]*?<\/span><\/p>/);
 assert.match(html,/<strong class="positive">\+0\.5000%<\/strong>/);
 const querySection=html.slice(html.indexOf('查詢 · 五分 60 棒'),html.indexOf('案例甲 · 原單進出場參考'));
 assert.doesNotMatch(querySection,/case-return-summary/);
});

test('full holding coverage describes source gaps rather than intentionally omitted middle',()=>{
 const data={snapshot_id:'full-hold',query_as_of_utc:200000,query:{'5m':[candle(300)],'1h':[candle(0)]},cases:[{
  ref:'案例甲',as_of_utc:600,'5m':[candle(300)],'1h':[candle(0)],execution:{status:'AVAILABLE',reason:'來源參考',mode:'FULL_HOLDING',bars:[candle(600),candle(900),candle(1500)],close_bars:[],markers:[],
   coverage:{scope:'WHOLE_REFERENCE_HOLDING' as const,calendar_slots:4,available_bars:3,gap_slots:1}}
 }]};
 const html=renderToStaticMarkup(createElement(CaseComparisonCharts,{data,light:false}));
 assert.match(html,/持倉已載入 3 根五分K/);
 assert.match(html,/來源時間間隔/);
 assert.doesNotMatch(html,/中間時段未展開/);
 assert.match(html,/休市或來源缺漏/);
});
