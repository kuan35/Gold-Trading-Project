import {test} from 'node:test';
import assert from 'node:assert/strict';
import {DemoEngine} from '../src/demo';

test('synthetic case order depends on direction only while draft still validates lot',()=>{
 const e=new DemoEngine();
 const r=e.retrieve('BUY','FIRST','0.1','0.1');
 const changed=e.retrieve('BUY','ADD','9');
 assert(r.total>0);
 assert.deepEqual(r.cases.map(c=>c.id),changed.cases.map(c=>c.id));
 assert(r.cases.every(c=>c.distance===null));
 assert.equal(r.comparison?.basis,'direction_only');
 const draft=e.draft('BUY','0.1',null,null,'0.1');
 assert.equal(draft.retrieval.comparison?.basis,'direction_only');
 assert.throws(()=>e.draft('BUY','0.1',null,null,'NaN'));
});

test('direction-only public case pool never claims market evidence',()=>{
 const r=new DemoEngine().retrieve('BUY','FIRST','0.1');
 assert.equal(r.comparison?.basis,'direction_only');
 assert.notEqual(r.sufficiency?.status,'usable');
 assert.equal(r.sufficiency?.is_success_probability,false);
 assert(r.profit_cases&&r.loss_cases);
 assert(r.cases.every(c=>c.distance===null&&c.differences.length));
});
