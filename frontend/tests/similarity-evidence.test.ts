import {test} from 'node:test';
import assert from 'node:assert/strict';
import {DemoEngine} from '../src/demo';
import {poolDescription,comparisonValue} from '../src/similarityPresentation';

test('public demo explicitly reports direction-only synthetic evidence',()=>{
 const r=new DemoEngine().retrieve('BUY','FIRST','.1');
 assert.equal(r.comparison?.mode,'operation_only');
 assert.equal(r.comparison?.market_matches,0);
 assert(r.cases.every(c=>c.distance===null));
 assert(r.cases.every(c=>c.market_comparison?.status==='unavailable'));
 const text=poolDescription(r);
 assert.match(text.market,/無法比較/);
 assert.doesNotMatch(text.market,/盤面條件接近/);
});

test('candidate mode explains unverified clock and separate limited tier',()=>{
 const r=new DemoEngine().retrieve('BUY','FIRST','.1');
 r.comparison={...r.comparison!,mode:'candidate_market',clock_status:'UNKNOWN',basis:'direction_and_market',
  reason:'券商時鐘未核實；尚未盲評'};
 r.five_minute_only_total=3;
 const text=poolDescription(r);
 assert.match(text.market,/候選盤面/);
 assert.match(text.market,/五分鐘限定/);
 assert.match(text.operation,/只篩買進／賣出方向/);
 assert.doesNotMatch(text.operation,/手數權重|40%|60%/);
});

test('empty strict market pool explains rejection without relabeling operation candidates as matches',()=>{
 const r=new DemoEngine().retrieve('BUY','FIRST','.1');
 r.total=0;r.cases=[];
 r.comparison={...r.comparison!,mode:'market_and_operation',market_features_enabled:true,
  market_matches:0,operation_candidates:10,verified_market_candidates:3,
  reason:'沒有同時通過操作與盤面條件的案例'};
 const text=poolDescription(r);
 assert.match(text.market,/沒有/);
 assert.match(text.operation,/10/);
 assert.doesNotMatch(text.market,/10.*接近/);
});

test('comparison values are readable without rounding unknown to zero',()=>{
 assert.equal(comparisonValue('1.428571428571428571'), '1.429');
 assert.equal(comparisonValue(null), '資料不足');
 assert.equal(comparisonValue('0'), '0');
 assert.equal(comparisonValue('NaN'), '資料不足');
});
