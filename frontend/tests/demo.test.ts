import {test} from 'node:test';
import assert from 'node:assert/strict';
import {DemoEngine} from '../src/demo';

test('review, cancel, explicit confirmation and retries preserve order integrity',()=>{
 const e=new DemoEngine();const d=e.draft('BUY','0.10');
 assert.equal(e.state().positions.length,0);assert.equal(d.risk.stop_loss_usd,null);
 e.cancel(d.id);assert.throws(()=>e.confirm(d.id,d.revision,'cancel'));
 const next=e.draft('BUY','0.10');const r=e.confirm(next.id,next.revision,'once');
 assert.equal(e.confirm(next.id,next.revision,'once').order_id,r.order_id);
 assert.equal(e.state().positions.length,1);
 const add=e.draft('BUY','0.10');assert.equal(add.action,'ADD');
 assert.equal(add.risk.after_lot,'0.2');
 e.step(1);assert.throws(()=>e.confirm(add.id,add.revision,'stale'),/更新/);
 assert.equal(e.chart('5m').markers.length,1);
});
test('decimal accounting handles spread, all-position scenarios and close',()=>{
 const e=new DemoEngine();const d=e.draft('BUY','0.10');
 assert.equal(d.risk.scenarios[0].loss,'53.00');
 e.confirm(d.id,d.revision,'open');
 const add=e.draft('BUY','0.10');assert.equal(add.risk.scenarios[0].loss,'106.00');
 const p=e.state().positions[0];const r=e.close(p.id,'close');
 assert.equal(r.state.account.balance,'9997.00');assert.equal(r.state.positions.length,0);
 e.close(p.id,'close');assert.equal(e.state().account.balance,'9997.00');
});
test('unsupported broker mode cannot trade; reset does not reuse old ids',()=>{
 const e=new DemoEngine();const d=e.draft('SELL','0.10');e.mode='broker_demo';
 assert.throws(()=>e.draft('BUY','0.1'),/未連線/);assert.throws(()=>e.confirm(d.id,d.revision,'x'));
 e.mode='replay';e.reset();assert.throws(()=>e.confirm(d.id,d.revision,'x'));
 assert.throws(()=>e.draft('BUY','NaN'));assert.throws(()=>e.draft('BUY','0.001'));
 assert.throws(()=>e.draft('BUY','0.1',e.state().quote.ask));
});
test('closed-bar chart never exposes future bars and cases remain synthetic',()=>{
 const e=new DemoEngine();for(const interval of ['5m','15m','1h'] as const){
  const seconds=interval==='5m'?300:interval==='15m'?900:3600;
  assert(e.chart(interval).bars.every(b=>b.time+seconds<=Number(e.state().clock)));
 }
 const r=e.retrieve('BUY','FIRST','0.1');assert.equal(r.total,r.wins+r.losses+r.flat+r.unknown);
 assert(r.cases.every(c=>c.source_kind==='synthetic_demo'));
 const old=e.rank('BUY','FIRST','0.1').map(c=>[c.id,c.distance]);
 e.cases.forEach(c=>{c.profit=String(-Number(c.profit));});
 assert.deepEqual(e.rank('BUY','FIRST','0.1').map(c=>[c.id,c.distance]),old);
 assert.throws(()=>e.caseDetail('secret'));
});
