import test from 'node:test';import assert from 'node:assert/strict';
import {executionDisplay,executionFocusRange} from '../src/caseExecutionDisplay';
import type {Marker} from '../src/types';
const bar=(time:number)=>({time,open:100,high:102,low:99,close:101});
const entry:Marker={time:600,position:'belowBar',color:'green',shape:'arrowUp',action:'ENTRY',text:'進場參考'};
const exit:Marker={time:100500,position:'aboveBar',color:'red',shape:'arrowDown',action:'CLOSE',text:'平倉參考'};

test('long-held trade uses one time-sorted chart, with explicit gaps and no invented bars',()=>{
 const before=[bar(0),bar(300)],record={status:'AVAILABLE',reason:'reference',bars:[bar(600)],close_bars:[bar(100200),bar(100500)],markers:[entry,exit]};
 const original=JSON.stringify({before,record});
 const display=executionDisplay(before,record);
 assert.deepEqual(display.bars.map(b=>b.time),[0,300,600,100200,100500]);
 assert.deepEqual(display.gaps,[{from:600,to:100200,missingSlots:331}]);
 assert.ok(display.markers.some(m=>m.action==='CLOSE'&&m.time===100500));
 assert.ok(display.markers.some(m=>m.time===100200&&m.text==='時間間隔'));
 assert.equal(JSON.stringify({before,record}),original);
});

test('same-bar entry and exit keep both markers but only one candle',()=>{
 const record={status:'AVAILABLE',reason:'reference',bars:[bar(600)],close_bars:[bar(600)],markers:[entry,{...exit,time:600}]};
 const display=executionDisplay([bar(300)],record);
 assert.deepEqual(display.bars.map(b=>b.time),[300,600]);
 assert.equal(display.markers.filter(m=>m.time===600).length,2);
 assert.equal(display.gaps.length,0);
});

test('conflicting overlap, invalid candles and unavailable execution are never silently merged',()=>{
 const record={status:'AVAILABLE',reason:'reference',bars:[bar(600)],close_bars:[{...bar(600),close:100}],markers:[entry]};
 assert.equal(executionDisplay([bar(300)],record).bars.length,0);
 assert.match(executionDisplay([bar(300)],record).reason,/衝突/);
 assert.equal(executionDisplay([bar(300)],{...record,close_bars:[{...bar(900),close:NaN}]}).bars.length,0);
 assert.equal(executionDisplay([bar(300)],{...record,status:'UNAVAILABLE',reason:'出場缺棒'}).reason,'出場缺棒');
 assert.equal(executionDisplay([bar(300)],undefined).bars.length,0);
});

test('focus jumps to the exact execution bar and stays in its contiguous segment',()=>{
 const bars=[bar(0),bar(300),bar(600),bar(100200),bar(100500)];
 assert.deepEqual(executionFocusRange(bars,[entry,exit],'CLOSE'),{from:3,to:4});
 const entryWindow=executionFocusRange(bars,[entry,exit],'ENTRY')!;
 assert.deepEqual(entryWindow,{from:0,to:2});
 assert.deepEqual(bars.slice(entryWindow.from,entryWindow.to+1).map(b=>b.time),[0,300,600]);
 assert.equal(executionFocusRange(bars,[entry],'CLOSE'),null);
 assert.equal(executionFocusRange(bars,[{...exit,time:100800}],'CLOSE'),null);
});

test('single-bar focus isolates the segment so chart minimum zoom cannot reveal other days',()=>{
 const bars=[bar(0),bar(600),bar(100200)];
 const window=executionFocusRange(bars,[entry],'ENTRY')!;
 assert.deepEqual(window,{from:1,to:1});
 assert.deepEqual(bars.slice(window.from,window.to+1).map(b=>b.time),[600]);
});
