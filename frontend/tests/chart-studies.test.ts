import test from 'node:test';import assert from 'node:assert/strict';
import {ChartStudyLayer,type StudyChart} from '../src/chartStudies';
import {studyValues,type Candle,type Study} from '../src/chartWorkspaceModel';
type Point={time:number;value:number;color?:string};
function harness(){
 const records:{title:string;pane:number;data:Point[];sets:number;updates:number;removed:boolean}[]=[];
 let removes=0,layoutWrites=0;const weights=[3];
 const chart={addSeries(_kind:unknown,options:{title?:string},pane=0){
  while(weights.length<=pane)weights.push(1);
  const r={title:options.title??'volume',pane,data:[] as Point[],sets:0,updates:0,removed:false};records.push(r);
  return {setData(data:Point[]){r.sets++;r.data=data.map(p=>({...p}));},update(p:Point){r.updates++;if(r.data.at(-1)?.time===p.time)r.data[r.data.length-1]={...p};else r.data.push({...p});},priceScale(){return {applyOptions(){}};},record:r};
 },removeSeries(s:{record:typeof records[number]}){removes++;s.record.removed=true;},panes(){return weights.map((_,i)=>({setStretchFactor(v:number){layoutWrites++;weights[i]=v;}}));}};
 return {chart:chart as unknown as StudyChart,records,weights,get removes(){return removes;},get layoutWrites(){return layoutWrites;}};
}
const bars=(n=80):Candle[]=>Array.from({length:n},(_,i)=>({time:1000+i*300,open:100+i*.1,high:102+i*.1,low:99+i*.1,close:101+i*.1,volume:i+10}));
test('MACD and signal retain series, user pane sizes and data through 80 ticks',()=>{
 const h=harness(),layer=new ChartStudyLayer(h.chart,true);let data=bars();layer.update(['MACD','MACDsignal'],data,true);
 assert.equal(h.records.length,2);assert.deepEqual(h.records.map(r=>r.pane),[1,1]);const writes=h.layoutWrites;h.weights[0]=7;h.weights[1]=2;
 for(let i=0;i<80;i++){data=data.map((b,j)=>j===79?{...b,close:110+i*.01}:b);layer.update(['MACD','MACDsignal'],data,true);}
 assert.equal(h.records.length,2);assert.equal(h.removes,0);assert.equal(h.layoutWrites,writes);assert.deepEqual(h.weights,[7,2]);
 for(const r of h.records){assert.equal(r.sets,1);assert.ok(r.updates>0);assert.deepEqual(r.data,studyValues(r.title as Study,data));}
});
test('new bars, old-bar corrections and shared MACD panes keep indicator data correct',()=>{
 const h=harness(),layer=new ChartStudyLayer(h.chart,true),selection:Study[]=['RSI14','MACD','MACDsignal','ATR14'];
 layer.update(selection,bars(),true);assert.deepEqual(h.records.map(r=>r.pane),[1,2,2,3]);layer.update(selection,bars(81),true);
 const corrected=bars(81).map((b,i)=>i===20?{...b,close:b.close-.3}:b);layer.update(selection,corrected,true);
 assert.equal(h.records.length,4);assert.equal(h.removes,0);for(const r of h.records)assert.deepEqual(r.data,studyValues(r.title as Study,corrected));
});
test('warmup stays missing and unchanged renders or native volume toggle do not rebuild studies',()=>{
 const h=harness(),layer=new ChartStudyLayer(h.chart,true);layer.update(['MACDsignal'],bars(20),true);assert.deepEqual(h.records[0].data,[]);
 layer.update(['MACDsignal'],bars(40),true);assert.deepEqual(h.records[0].data,studyValues('MACDsignal',bars(40)));
 const calls=[h.records[0].sets,h.records[0].updates];layer.update(['MACDsignal'],bars(40),false);
 assert.equal(h.records.length,1);assert.equal(h.removes,0);assert.deepEqual([h.records[0].sets,h.records[0].updates],calls);
});
test('fallback tick overlay updates without reconstruction and never fills unknown volume with zero',()=>{
 const h=harness(),layer=new ChartStudyLayer(h.chart,false);const data=bars().map((b,i)=>i===10?{...b,volume:undefined}:b);layer.update(['SMA20'],data,true);
 assert.equal(h.records.length,2);assert.equal(h.records[1].data.length,79);
 layer.update(['SMA20'],data.map((b,i)=>i===79?{...b,volume:1000}:b),true);assert.equal(h.records.length,2);assert.equal(h.removes,0);assert.equal(h.records[1].data.at(-1)?.value,1000);
 layer.update(['SMA20'],data,false);assert.equal(h.records.filter(r=>!r.removed).length,1);layer.dispose();assert.equal(h.records.filter(r=>!r.removed).length,0);
});
test('explicit study changes and teardown remove owned series, disposal is idempotent',()=>{
 const h=harness(),layer=new ChartStudyLayer(h.chart,true);layer.update(['MACD','MACDsignal'],bars(),true);layer.update(['MACD'],bars(),true);
 assert.equal(h.records.filter(r=>!r.removed).length,1);layer.dispose();assert.equal(h.records.filter(r=>!r.removed).length,0);layer.dispose();assert.equal(h.removes,h.records.length);
});
