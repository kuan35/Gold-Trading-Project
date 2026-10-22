import {test} from 'node:test';import assert from 'node:assert/strict';
import {layerCoordinate} from '../src/analysisChartCoordinates';
test('region right edge at closed-bar cutoff uses logical next bar instead of missing exact timestamp',()=>{
 const bars=[{time:300},{time:600},{time:900}];const exact=(n:number)=>({300:10,600:20,900:30}[n]??null);const logical=(n:number)=>10+n*10;
 assert.equal(layerCoordinate(1200,bars,exact,logical),40);assert.equal(layerCoordinate(600,bars,exact,logical),20);assert.equal(layerCoordinate(1300,bars,exact,logical),null);
});
