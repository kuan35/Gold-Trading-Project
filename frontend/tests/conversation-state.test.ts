import {test} from 'node:test';
import assert from 'node:assert/strict';
import {emptyInput,patchInput,missingInput,acceptRevision,submissionLocked,discussionSide} from '../src/conversationState';
test('no implicit direction, type or lot; optional protection remains blank',()=>{
 assert.deepEqual(missingInput(emptyInput()),['方向','單型','手數']);
 const s=patchInput(emptyInput(),{side:'SELL',order_type:'LIMIT',lot:'.20',limit_price:'4200'});
 assert.deepEqual(missingInput(s),[]);assert.equal(s.sl,'');assert.equal(s.side,'SELL');
 assert.deepEqual(missingInput({...s,limit_price:''}),['限價']);
});
test('explicit clearing only touches supplied fields and stale requests cannot apply',()=>{
 const s=patchInput({...emptyInput(),side:'BUY',sl:'4000',tp:'4300'},{sl:null});
 assert.equal(s.sl,'');assert.equal(s.tp,'4300');assert.equal(s.side,'BUY');
 assert.equal(acceptRevision(4,5),false);assert.equal(acceptRevision(5,5),true);
});
test('unresolved submissions remain locked including unknown status and filled before account refresh',()=>{
 for(const status of ['UNKNOWN','ACCEPTED','PARTIALLY_FILLED','UNRECOGNIZED'])assert.equal(submissionLocked(status),true);
 assert.equal(submissionLocked('FILLED'),true);assert.equal(submissionLocked('FILLED','2026-10-22T01:00:00Z','2026-10-22T01:00:01Z'),false);
 assert.equal(submissionLocked('REJECTED'),false);
});
test('side-less stop edit preserves known analysis direction without adding an order side',()=>{
 assert.equal(discussionSide(null,'BUY','SELL'),'BUY');assert.equal(discussionSide('SELL','BUY','BUY'),'SELL');assert.equal(discussionSide(null,null,'SELL'),'SELL');assert.equal(discussionSide(null,null,null),null);
});
