import test from 'node:test';import assert from 'node:assert/strict';
import {DraftAgentSession} from '../src/draftAgent';
const draft={id:'draft-a',analysis_snapshot_id:'snapshot-a',analysis_as_of_utc:'2000-01-01T00:00:00Z'};
const reply={snapshot_id:draft.analysis_snapshot_id,as_of_utc:draft.analysis_as_of_utc,analysis_mode:'draft_snapshot',market_status:'FROZEN',provider:'claude_market_analysis'};
test('agent only reads the original draft and forwards selected model options',async()=>{
 let path='',body:any;const session=new DraftAgentSession();const got:any[]=[];
 await session.start(draft,{provider:'claude_code',model:'sonnet',effort:'high'},async(p,b)=>{path=p;body=b;return reply as any;},r=>got.push(r));
 assert.equal(path,'/assistant/draft-chat');assert.equal(body.draft_id,draft.id);assert.equal(body.llm_enabled,true);assert.equal(body.effort,'high');assert.equal(got.length,1);
 assert.equal(body.confirmed,undefined);assert.equal(body.snapshot,undefined);
 assert.match(body.message,/已填的方向、單型、手數/);assert.match(body.message,/這筆委託評估/);
});
test('late responses from a cancelled or superseded check cannot overwrite another draft',async()=>{
 let resolve!:(r:any)=>void;const session=new DraftAgentSession(),got:any[]=[];
 const old=session.start(draft,{},()=>new Promise(r=>resolve=r),r=>got.push(r));session.cancel();resolve(reply);await old;assert.equal(got.length,0);
 await session.start(draft,{},async()=>({...reply,snapshot_id:'other'}) as any,r=>got.push(r));assert.equal(got[0].status,'error');
});
