import test from 'node:test';import assert from 'node:assert/strict';
import {studyValues,decodeDrawings,DrawingHistory} from '../src/chartWorkspaceModel';
import {buildDialogueMemory} from '../src/dialogueMemory';
import {protectionChanges} from '../src/BrokerPositionActions';
import {createElement} from 'react';import {renderToStaticMarkup} from 'react-dom/server';import AnalysisChart from '../src/AnalysisChart';
import {relativeRange} from '../src/chartComparisonSync';
test('studies keep warmup missing and calculate deterministic SMA EMA RSI ATR bands',()=>{
 const bars=Array.from({length:65},(_,i)=>({time:i+1,open:100+i,close:101+i,high:102+i,low:99+i,volume:10}));
 assert.deepEqual(studyValues('SMA20',bars).map(p=>p.time).slice(0,2),[20,21]);
 assert.equal(studyValues('SMA20',bars)[0].value,110.5);
 assert.equal(studyValues('EMA20',bars)[0].value,110.5);
 assert.equal(studyValues('RSI14',bars).at(-1)?.value,100);
 assert.equal(studyValues('ATR14',bars).at(-1)?.value,3);
 assert.equal(studyValues('SMA60',bars.slice(0,20)).length,0);
 assert.ok(studyValues('BBupper',bars)[0].value>studyValues('SMA20',bars)[0].value);
});
test('drawing history is scoped and validates stored coordinates with undo redo',()=>{
 const h=new DrawingHistory();h.push([{id:'x',kind:'horizontal',points:[{time:10,price:20}],text:''}]);
 assert.equal(h.undo().length,0);assert.equal(h.redo()[0].id,'x');
 const raw=JSON.stringify({scope:'case-A',drawings:h.current});
 assert.equal(decodeDrawings(raw,'case-A').length,1);assert.equal(decodeDrawings(raw,'case-B').length,0);
 assert.equal(decodeDrawings(JSON.stringify({scope:'case-A',drawings:[{id:'x',kind:'trend',points:[{time:10,price:null}]}]}),'case-A').length,0);
});
test('dialogue whitelist is bounded and protection keep clear are explicit',()=>{
 const memory=buildDialogueMemory(Array.from({length:9},()=>({question:'問題',record:{answer:'舊分析'},confirm:true})),'thread');
 assert.equal(memory.length,6);assert.deepEqual(Object.keys(memory[0]),['thread_id','question','answer']);
 assert.deepEqual(protectionChanges('KEEP','','CLEAR',''),{tp:null});
 assert.deepEqual(protectionChanges('SET',' 4000 ','KEEP',''),{sl:'4000'});
 assert.throws(()=>protectionChanges('KEEP','','KEEP',''));
});
test('analysis storage uses explicit snapshot identity even with identical bars and labels',()=>{
 const frame={bars:[{time:100,open:10,high:12,low:9,close:11}],layers:[],quality:{}};
 const a=renderToStaticMarkup(createElement(AnalysisChart,{frame,light:false,ariaLabel:'分析5m',scope:'snapshot-A:5m'}));
 const b=renderToStaticMarkup(createElement(AnalysisChart,{frame,light:false,ariaLabel:'分析5m',scope:'snapshot-B:5m'}));
 assert.match(a,/data-drawing-scope="snapshot-A:5m"/);assert.match(b,/data-drawing-scope="snapshot-B:5m"/);
 assert.deepEqual(relativeRange({from:10,to:70},59),{from:-49,to:11});
});
