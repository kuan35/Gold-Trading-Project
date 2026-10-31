import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createElement} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import BrokerClosePanel,{brokerCloseReady,brokerCloseLocked,confirmBrokerClose,CloseConfirmError} from '../src/BrokerClosePanel';
import type {DemoMarket} from '../src/demoMarket';

const market={source:'ctrader_demo_xauusd',environment:'demo',connection_status:'CONNECTED',order_connection:true,token_scope:'TRADE',
  quote:{status:'CURRENT',bid:'2500',ask:'2500.30',age_seconds:1,source_time_utc:'2026-10-21T00:00:00Z'},
  symbol:{lot_size_cents:10000,min_volume_cents:100,max_volume_cents:100000,step_volume_cents:100,digits:2},
  account:{status:'CURRENT',balance:'1000',equity:'1010',currency:'USD',positions:[{id:'123',side:'BUY',volume_units:'10',entry:'2499',sl:null,tp:null}],pending_orders:[],
    all_positions_count:1,all_pending_orders_count:0,updated_at_utc:'2026-10-21T00:00:00Z'}} satisfies DemoMarket;

test('DEMO close control identifies its source and exposes a ready full-position action',()=>{
  const html=renderToStaticMarkup(createElement(BrokerClosePanel,{market,positionId:'123'}));
  assert.match(html,/>平倉<\/button>/);
  assert.match(html,/cTrader DEMO/);
  assert.match(html,/全部剩餘/);
  assert.doesNotMatch(html,/<button[^>]*disabled[^>]*>平倉<\/button>/);
  assert.equal(brokerCloseReady(market,'123'),true);
});

test('DEMO close is disabled without current quote/account/trading scope/position',()=>{
  const variants:Array<DemoMarket|null>=[null];
  for(const problem of ['scope','connection','quote','age','account','position','volume','symbol']){
    const next:DemoMarket=structuredClone(market);
    if(problem==='scope')next.token_scope='VIEW';
    if(problem==='connection')next.order_connection=false;
    if(problem==='quote')next.quote.status='STALE';
    if(problem==='age')next.quote.age_seconds=6;
    if(problem==='account')next.account!.status='STALE';
    if(problem==='position')next.account!.positions=[];
    if(problem==='volume')next.account!.positions[0].volume_units='0';
    if(problem==='symbol')next.symbol=null;
    variants.push(next);
  }
  for(const next of variants){
    assert.equal(brokerCloseReady(next,'123'),false);
    const html=renderToStaticMarkup(createElement(BrokerClosePanel,{market:next,positionId:'123'}));
    assert.match(html,/<button[^>]*disabled/);
    assert.match(html,/cTrader DEMO/);
    assert.doesNotMatch(html,/本機模擬成交/);
  }
});

test('typed close confirm distinguishes explicit validation rejection from uncertain transport without resending',async()=>{
  const original=globalThis.fetch;
  const cases=[{status:409,body:{detail:'草稿已超過 30 秒'},safe:true},
    {status:400,body:{detail:'版本無效'},safe:true},
    {status:503,body:{detail:'服務無法確認委託'},safe:false},
    {status:408,body:{detail:'逾時'},safe:false},
    {status:409,body:{error:'unknown proxy response'},safe:false}];
  try{
    for(const scenario of cases){
      let calls=0;
      globalThis.fetch=async(url,init)=>{
        calls++;
        assert.equal(url,'/api/broker/drafts/one/confirm');
        assert.deepEqual(JSON.parse(String(init?.body)),{revision:1,idempotency_key:'stable-key'});
        return new Response(JSON.stringify(scenario.body),{status:scenario.status,headers:{'content-type':'application/json'}});
      };
      await assert.rejects(confirmBrokerClose('one',1,'stable-key'),error=>
        error instanceof CloseConfirmError&&error.safeRejected===scenario.safe);
      assert.equal(calls,1);
    }
    let calls=0;
    globalThis.fetch=async()=>{calls++;throw new TypeError('network unavailable');};
    await assert.rejects(confirmBrokerClose('one',1,'stable-key'),/network unavailable/);
    assert.equal(calls,1);
  }finally{globalThis.fetch=original;}
});

test('filled close unlocks remaining volume only after a newer account reconciliation',()=>{
  assert.equal(brokerCloseLocked('UNKNOWN','2026-10-21T00:00:01Z','2026-10-21T00:00:02Z'),true);
  assert.equal(brokerCloseLocked('FILLED','2026-10-21T00:00:01Z','2026-10-21T00:00:00Z'),true);
  assert.equal(brokerCloseLocked('FILLED','2026-10-21T00:00:01Z','2026-10-21T00:00:01Z'),true);
  assert.equal(brokerCloseLocked('FILLED','2026-10-21T00:00:01Z','2026-10-21T00:00:02Z'),false);
  assert.equal(brokerCloseLocked('FILLED',undefined,'2026-10-21T00:00:02Z'),true);
  assert.equal(brokerCloseLocked('REJECTED',undefined,undefined),false);
});
