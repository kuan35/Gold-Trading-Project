import {test} from 'node:test';
import assert from 'node:assert/strict';
import {DemoEngine} from '../src/demo';

test('relative query uses prior-only synthetic baselines and preserves input in draft',()=>{
 const e=new DemoEngine();
 const r=e.retrieve('BUY','FIRST','0.1','0.1');
 assert.equal(r.comparison?.basis,'relative_lot');
 assert(r.total>0);
 assert(r.cases.every(c=>c.comparison_basis==='relative_lot'));
 const draft=e.draft('BUY','0.1',null,null,'0.1');
 assert.equal(draft.retrieval.comparison?.basis,'relative_lot');
 assert.throws(()=>e.draft('BUY','0.1',null,null,'NaN'));
});

test('cold query discloses absolute fallback and never labels it usable',()=>{
 const r=new DemoEngine().retrieve('BUY','FIRST','0.1');
 assert.equal(r.comparison?.basis,'absolute_lot');
 assert.notEqual(r.sufficiency?.status,'usable');
 assert.equal(r.sufficiency?.is_success_probability,false);
 assert(r.profit_cases&&r.loss_cases);
 assert(r.cases.every(c=>c.components?.length&&c.differences.length));
});
