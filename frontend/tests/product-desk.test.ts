import {test} from 'node:test';
import assert from 'node:assert/strict';
import {decodeArchive,encodeArchive,makeArchiveEntry,mergeArchive,needsAnalysis,changedFields} from '../src/deskConversations';
import {emptyInput} from '../src/conversationState';

test('conversation archive restores text only, never executable draft or confirmation data',()=>{
 const raw=JSON.stringify({version:1,items:[{id:'c1',title:'多單討論',updatedAt:10,turns:[{question:'改手數',answer:'已修改',at:'2026-10-23T01:00:00Z',draft:{id:'secret'},idempotency_key:'old-key',proposal:{side:'BUY'}}]}]});
 const restored=decodeArchive(raw);assert.equal(restored.items.length,1);assert.equal(restored.writable,true);
 assert.deepEqual(Object.keys(restored.items[0].turns[0]).sort(),['answer','at','question']);
 assert.doesNotMatch(encodeArchive(restored.items),/old-key|secret|proposal/);
});
test('bad or future storage is preserved rather than silently overwritten',()=>{
 for(const raw of ['broken','{"version":5,"items":[]}','{"version":1,"items":[{"id":"bad"}]}']){
  const value=decodeArchive(raw);assert.equal(value.writable,false);assert.ok(value.error);assert.deepEqual(value.items,[]);
 }
 assert.deepEqual(decodeArchive(null),{items:[],writable:true,error:''});
});
test('archive has bounded conversations and turns and masks accidental provider keys',()=>{
 let items=Array.from({length:18},(_,i)=>makeArchiveEntry('c'+i,[{question:'q'+i,answer:'a',at:'2026-10-23T01:00:00Z'}],i));
 items=mergeArchive(items,makeArchiveEntry('latest',Array.from({length:28},()=>({question:'gsk_exampleSuperSecretToken1234567890',answer:'x'.repeat(4000),at:'2026-10-23T01:00:00Z'})),100));
 assert.equal(items.length,12);assert.equal(items[0].id,'latest');assert.equal(items[0].turns.length,20);
 assert.ok(items[0].turns.every(t=>t.answer.length<=1800));assert.doesNotMatch(encodeArchive(items),/exampleSuperSecret/);
 assert.equal(mergeArchive(items,items[0]).filter(i=>i.id==='latest').length,1);
});
test('numeric edits give a concise delta while direction changes still refresh market cases',()=>{
 assert.equal(needsAnalysis('EDIT',{lot:'0.20'},'BUY','BUY',true),false);
 assert.equal(needsAnalysis('EDIT',{sl:'3990'},'BUY','BUY',false),false);
 assert.equal(needsAnalysis('EDIT',{side:'SELL'},'BUY','SELL',true),true);
 assert.equal(needsAnalysis('PREPARE',{side:'BUY'},null,'BUY',false),true);
 assert.equal(needsAnalysis('DISCUSS',{},'BUY','BUY',true),true);
 assert.equal(needsAnalysis('CLARIFY',{},null,null,false),false);
 const before={...emptyInput(),side:'BUY' as const,lot:'0.10'},after={...before,lot:'0.20',sl:'3990'};
 assert.deepEqual(changedFields(before,after),['手數 0.10 → 0.20','停損 未設定 → 3990']);
});
