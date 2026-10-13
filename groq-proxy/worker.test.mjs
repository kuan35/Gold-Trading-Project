import {test} from 'node:test';
import assert from 'node:assert/strict';
import {handleRequest} from './worker.mjs';

const env={GROQ_API_KEY:'test-only-key',TURNSTILE_SECRET_KEY:'test-only-secret',GROQ_LIMITER:{limit:async()=>({success:true})}};
const request=(origin='https://kuan35.github.io',body={message:'分析目前行情',facts:'合成回放；K線比對未核實',token:'challenge'})=>new Request('https://proxy.example/explain',{
  method:'POST',headers:{Origin:origin,'Content-Type':'application/json'},body:JSON.stringify(body),
});

test('rejects wrong origin and missing secrets before upstream calls',async()=>{
  const blocked=await handleRequest(request('https://evil.example'),env,()=>{throw Error('called');});
  assert.equal(blocked.status,403);
  const missing=await handleRequest(request(),{},()=>{throw Error('called');});
  assert.equal(missing.status,503);
});

test('rejects oversized body without upstream calls',async()=>{
  const result=await handleRequest(request('https://kuan35.github.io',{message:'x'.repeat(4100),facts:'',token:'challenge'}),env,()=>{throw Error('called');});
  assert.equal(result.status,413);
});

test('rejects invalid or wrong-host Turnstile token without calling Groq',async()=>{
  const calls=[];
  const fetcher=async url=>{calls.push(url);return Response.json({success:true,hostname:'evil.example',action:'gold_desk_chat'});};
  const result=await handleRequest(request(),env,fetcher);
  assert.equal(result.status,403);
  assert.deepEqual(calls,['https://challenges.cloudflare.com/turnstile/v0/siteverify']);
});

test('forwards only bounded explanation request after Turnstile validation',async()=>{
  const calls=[];
  const fetcher=async(url,options)=>{
    calls.push({url,options});
    return url.includes('siteverify')?Response.json({success:true,hostname:'kuan35.github.io',action:'gold_desk_chat'}):Response.json({choices:[{message:{content:'合成回放資料顯示區間波動；歷史盤面尚未核實。'}}]});
  };
  const result=await handleRequest(request(),env,fetcher);
  assert.equal(result.status,200);
  assert.equal((await result.json()).provider,'groq_explanation');
  assert.equal(calls.length,2);
  const sent=JSON.parse(calls[1].options.body);
  assert.equal(sent.messages.length,2);
  assert.match(sent.messages[0].content,/不能聲稱歷史K線相似/);
  assert.ok(sent.max_completion_tokens>=512);
  assert.equal(sent.reasoning_effort,'low');
  assert.equal(result.headers.get('Cache-Control'),'no-store');
});

test('does not display a Groq reply cut off by the completion limit',async()=>{
  const fetcher=async url=>url.includes('siteverify')
    ?Response.json({success:true,hostname:'kuan35.github.io',action:'gold_desk_chat'})
    :Response.json({choices:[{finish_reason:'length',message:{content:'這段說明還沒寫完，接下來'}}]});
  const result=await handleRequest(request(),env,fetcher);
  assert.equal(result.status,502);
  assert.match((await result.json()).error,/回答未完整/);
});

test('rate limit prevents Groq call',async()=>{
  const calls=[];
  const limited={...env,GROQ_LIMITER:{limit:async()=>({success:false})}};
  const fetcher=async url=>{calls.push(url);return Response.json({success:true,hostname:'kuan35.github.io',action:'gold_desk_chat'});};
  const result=await handleRequest(request(),limited,fetcher);
  assert.equal(result.status,429);
  assert.equal(calls.length,1);
});
