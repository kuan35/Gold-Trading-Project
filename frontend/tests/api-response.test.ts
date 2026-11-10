import test from 'node:test';import assert from 'node:assert/strict';
import {readAPIResponse} from '../src/api';
test('non-JSON server failures are reported as server errors without exposing their body',async()=>{
 await assert.rejects(()=>readAPIResponse(new Response('<html>PRIVATE_TRACEBACK</html>',{status:500})),e=>{
  assert(e instanceof Error);assert.match(e.message,/500/);assert.doesNotMatch(e.message,/後端已啟動|PRIVATE_TRACEBACK|html/);return true;
 });
});
test('successful malformed responses are rejected and domain reasons survive JSON errors',async()=>{
 await assert.rejects(()=>readAPIResponse(new Response('not-json',{status:200})),/回應格式/);
 await assert.rejects(()=>readAPIResponse(new Response(JSON.stringify({detail:'停損方向錯誤'}),{status:409})),/停損方向錯誤/);
 assert.deepEqual(await readAPIResponse(new Response('{"status":"READY"}')),{status:'READY'});
});
