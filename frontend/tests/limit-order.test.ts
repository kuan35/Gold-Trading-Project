import {test} from 'node:test';
import assert from 'node:assert/strict';
import Decimal from 'decimal.js';
import {DemoEngine} from '../src/demo';

test('browser buy limit stays pending until synthetic ask touches it',()=>{
 const engine=new DemoEngine(),limit=new Decimal(engine.quote().ask).minus(2).toFixed(2);
 const draft=engine.draft('BUY','0.10',null,null,null,'LIMIT',limit);
 const receipt=engine.confirm(draft.id,draft.revision,'once');
 assert.equal(receipt.status,'PENDING');assert.equal(engine.state().positions.length,0);
 assert.equal(engine.confirm(draft.id,draft.revision,'once').order_id,receipt.order_id);
 engine.bars[engine.cursor]={...engine.bars[engine.cursor],open:String(Number(limit)+3),high:String(Number(limit)+4),low:String(Number(limit)+1),close:String(Number(limit)+2)};
 engine.step(1);assert.equal(engine.state().positions.length,0);
 engine.bars[engine.cursor]={...engine.bars[engine.cursor],open:String(Number(limit)+1),high:String(Number(limit)+2),low:String(Number(limit)-.3),close:limit};
 engine.step(1);assert.equal(engine.state().positions.length,1);
 assert.equal(engine.state().positions[0].entry,limit);assert.equal(engine.state().pending_orders.length,0);
});

test('browser sell limit can be cancelled and broker mode rejects it',()=>{
 const engine=new DemoEngine(),bid=new Decimal(engine.quote().bid);
 assert.throws(()=>engine.draft('SELL','0.10',null,null,null,'LIMIT',bid.toFixed(2)),/高於/);
 const draft=engine.draft('SELL','0.10',null,null,null,'LIMIT',bid.plus(2).toFixed(2));
 const receipt=engine.confirm(draft.id,draft.revision,'sell');
 engine.cancelPending(receipt.order_id);
 engine.bars[engine.cursor]={...engine.bars[engine.cursor],open:bid.toString(),high:bid.plus(3).toString(),low:bid.minus(1).toString(),close:bid.plus(2).toString()};
 engine.step(1);assert.equal(engine.state().positions.length,0);
 engine.mode='broker_demo';assert.throws(()=>engine.draft('BUY','0.10',null,null,null,'LIMIT',bid.minus(2).toFixed(2)),/未連線/);
});
