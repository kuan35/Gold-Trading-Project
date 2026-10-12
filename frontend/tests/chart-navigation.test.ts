import {test} from 'node:test';
import assert from 'node:assert/strict';
import {DemoEngine} from '../src/demo';

test('new fills are visible immediately at price, and close focuses both ends',()=>{
  const e=new DemoEngine(),draft=e.draft('BUY','0.10');
  const entry=e.confirm(draft.id,draft.revision,'open').order_id;
  const marker=e.chart().markers.find(m=>m.id===entry);
  assert.equal(marker?.price,draft.price);
  assert.equal(marker?.executed_at,e.clock);
  const exit=e.close(entry,'close').order_id;
  const chart=e.chart('5m',exit);
  assert.deepEqual(new Set(chart.focus?.order_ids),new Set([entry,exit]));
  assert(chart.bars.every(b=>b.time+300<=e.clock));
  assert.throws(()=>e.chart('5m','missing'));
});
