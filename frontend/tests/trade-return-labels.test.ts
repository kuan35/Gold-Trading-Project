import test from 'node:test';import assert from 'node:assert/strict';
import {executionReturnMarkers,priceReturnDisplay,type PriceResult} from '../src/TradeResult';
import type {Marker} from '../src/types';
const result=(value:string|null):PriceResult=>({status:'AVAILABLE',price_return_pct:value,move_per_oz:null,margin_roi_pct:null,reason:'fixture'});

test('return labels retain signs and zero, and reject missing or invalid values',()=>{
 assert.deepEqual(priceReturnDisplay(result('0.5')),{text:'+0.5000%',tone:'positive'});
 assert.deepEqual(priceReturnDisplay(result('-0.25')),{text:'-0.2500%',tone:'negative'});
 assert.deepEqual(priceReturnDisplay(result('0')),{text:'0.0000%',tone:''});
 for(const value of [null,'','NaN','Infinity','garbage'])assert.deepEqual(priceReturnDisplay(result(value)),{text:'未提供',tone:''});
 assert.equal(priceReturnDisplay({...result('0.5'),status:'UNAVAILABLE'}).text,'未提供');
});

test('only the exit annotation receives the historical return; source markers stay intact',()=>{
 const markers:Marker[]=[
  {time:600,position:'belowBar',color:'green',shape:'arrowUp',text:'進場參考',action:'ENTRY'},
  {time:900,position:'aboveBar',color:'red',shape:'arrowDown',text:'平倉參考',action:'CLOSE'}
 ];
 const annotated=executionReturnMarkers(markers,result('-0.25'));
 assert.equal(annotated[0].text,'進場參考');
 assert.equal(annotated[1].text,'平倉參考 · 價格報酬率（未扣交易成本） -0.2500%');
 assert.equal(annotated[1].time,900);assert.equal(markers[1].text,'平倉參考');
 assert.deepEqual(executionReturnMarkers(markers,result(null)),markers);
 assert.match(executionReturnMarkers(markers,result('0'))[1].text,/0\.0000%/);
});
