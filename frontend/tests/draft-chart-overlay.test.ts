import test from 'node:test';
import assert from 'node:assert/strict';
import {createElement} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import DraftChartOverlay,{draftChartLevels,priceFromY,stepDraftPrice,DraftPriceLines,draftChartGeometry,
 type DraftChartState,type DraftLineSeries} from '../src/DraftChartOverlay';

const draft=(changes:Partial<DraftChartState>={}):DraftChartState=>({side:'BUY',order_type:'LIMIT',
 limit_price:'4000',sl:'3990',tp:'4020',digits:2,onPatch:()=>{},...changes});

test('limit uses specified entry and valid stops while market uses executable entry read-only',()=>{
 assert.deepEqual(draftChartLevels(draft()).map(l=>[l.key,l.price,l.draggable]),
  [['entry',4000,true],['sl',3990,true],['tp',4020,true]]);
 assert.deepEqual(draftChartLevels(draft({order_type:'MARKET',entry_price:'4000.20'})).map(l=>[l.key,l.price,l.draggable]),
  [['entry',4000.2,false],['sl',3990,true],['tp',4020,true]]);
 assert.equal(draftChartLevels(draft({disabled:true})).some(l=>l.draggable),false);
});

test('invalid direction entry and nonfinite values do not create draft levels',()=>{
 for(const change of [{side:null},{order_type:null},{limit_price:'NaN'},{limit_price:'0'},
  {order_type:'MARKET',entry_price:null},{limit_price:'Infinity'}] as Partial<DraftChartState>[])
  assert.deepEqual(draftChartLevels(draft(change)),[]);
 assert.deepEqual(draftChartLevels(draft({sl:'4001',tp:'3999'})).map(l=>l.key),['entry']);
 assert.deepEqual(draftChartLevels(draft({side:'SELL',sl:'4010',tp:'3980'})).map(l=>l.key),['entry','sl','tp']);
 assert.deepEqual(draftChartLevels(draft({sl:'NaN',tp:'0'})).map(l=>l.key),['entry']);
 assert.deepEqual(draftChartLevels(draft({digits:100})),[]);
});

test('pointer geometry accepts only visible candle pane and yields fixed digit price strings',()=>{
 const convert=(y:number)=>4100-y;
 assert.equal(priceFromY(50,100,convert,2),'4050.00');
 for(const y of [-1,101,NaN,Infinity])assert.equal(priceFromY(y,100,convert,2),null);
 assert.equal(priceFromY(1,0,convert,2),null);
 assert.equal(priceFromY(1,100,()=>null,2),null);
 assert.equal(priceFromY(1,100,()=>NaN,2),null);
 assert.equal(priceFromY(1,100,()=>0,2),null);
 assert.equal(priceFromY(1,100,convert,10),null);
});

test('keyboard adjusts a single broker display tick and market entry never becomes editable',()=>{
 assert.deepEqual(stepDraftPrice(draft(),'sl','ArrowUp'),{sl:'3990.01'});
 assert.deepEqual(stepDraftPrice(draft(),'tp','ArrowDown'),{tp:'4019.99'});
 assert.deepEqual(stepDraftPrice(draft(),'entry','ArrowDown'),{limit_price:'3999.99'});
 assert.equal(stepDraftPrice(draft({order_type:'MARKET',entry_price:'4000'}),'entry','ArrowUp'),null);
 assert.equal(stepDraftPrice(draft({disabled:true}),'sl','ArrowUp'),null);
 assert.equal(stepDraftPrice(draft(),'sl','Enter'),null);
});

test('risk and reward zones clip to candle pane instead of extending into indicator panes',()=>{
 const levels=draftChartLevels(draft());
 const geometry=draftChartGeometry(levels,price=>4100-price,120,500);
 assert.equal(geometry.lines.length,3);
 assert.deepEqual(geometry.zones.map(z=>[z.key,z.top,z.height]),[['sl',100,10],['tp',80,20]]);
 const clipped=draftChartGeometry(levels,price=>4100-price,90,500);
 assert.deepEqual(clipped.lines.map(l=>l.key),['tp']);
 assert.deepEqual(clipped.zones.map(z=>[z.key,z.top,z.height]),[['tp',80,10]]);
 assert.deepEqual(draftChartGeometry(levels,()=>NaN,100,500),{lines:[],zones:[]});
 assert.deepEqual(draftChartGeometry(levels,()=>50,0,500),{lines:[],zones:[]});
});

test('owned price lines update in place and disposal preserves unrelated chart annotations',()=>{
 const created:{price:number;updates:number;removed:boolean}[]=[];
 const series:DraftLineSeries={
  createPriceLine:options=>{const row={price:options.price!,updates:0,removed:false};created.push(row);
   return {applyOptions:patch=>{row.price=patch.price!;row.updates++;}} as ReturnType<DraftLineSeries['createPriceLine']>;},
  removePriceLine:line=>{const i=handles.indexOf(line);if(i>=0)created[i].removed=true;},
 };
 const handles:ReturnType<DraftLineSeries['createPriceLine']>[]=[];
 const original=series.createPriceLine;
 series.createPriceLine=options=>{const line=original(options);handles.push(line);return line;};
 series.createPriceLine({price:1}); // A different layer's annotation already exists.
 const layer=new DraftPriceLines(series);
 layer.update(draftChartLevels(draft()));assert.equal(created.length,4);
 layer.update(draftChartLevels(draft({entry_price:'4400',limit_price:'4000.20'})));
 assert.equal(created.length,4);assert.equal(created[1].price,4000.2);
 layer.update(draftChartLevels(draft({sl:''})));assert.equal(created[2].removed,true);
 layer.dispose();assert.ok(created.slice(1).every(row=>row.removed));assert.equal(created[0].removed,false);
 layer.dispose();
});

test('absent or disposed runtime renders no controls and cannot patch the draft',()=>{
 let patches=0;
 const d=draft({onPatch:()=>{patches++;}});
 assert.equal(renderToStaticMarkup(createElement(DraftChartOverlay,{runtime:null,draft:d})), '');
 assert.equal(patches,0);
});
