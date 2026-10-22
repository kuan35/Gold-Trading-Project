import {test} from 'node:test';
import assert from 'node:assert/strict';
import {mergeLiveBars,liveUpdateKind,interpolateClose,provisionalBarCount} from '../src/liveCandles';
const a={time:100,open:4,high:5,low:3,close:4,volume:7};
const b={...a,time:200,close:4.5,volume:8};

test('native closed bars override provisional candles without changing source arrays',()=>{
 const native=[a],pending=[{...a,volume:3},b];
 const live={...b,time:300,volume:9};
 assert.deepEqual(mergeLiveBars(native,pending,live),[a,b,live]);
 assert.equal(native.length,1);assert.equal(pending[0].volume,3);
 assert.equal(provisionalBarCount(native,pending),1);
 assert.equal(provisionalBarCount([a,b],pending),0);
});

test('same-time tick uses update and new bars append; native revisions reset only data',()=>{
 assert.equal(liveUpdateKind([a,b],[a,{...b,close:4.8}]),'update');
 assert.equal(liveUpdateKind([a],[a,b]),'update');
 assert.equal(liveUpdateKind([a,b],[{...a,high:6},b]),'reset');
 assert.equal(liveUpdateKind([a,b],[a]),'reset');
});

test('price tween stays inside true high/low and reaches exact tick; reduced motion jumps',()=>{
 const target={...a,close:3.5};
 assert.equal(interpolateClose(4,target,.5,false).close,3.5625);
 assert.equal(interpolateClose(4,target,1,false).close,3.5);
 assert.equal(interpolateClose(4,target,0,true).close,3.5);
 assert.equal(interpolateClose(99,target,0,false).close,5);
 assert.equal(interpolateClose(4,target,.5,false).high,5);
 assert.equal(interpolateClose(4,target,.5,false).volume,7);
});
