import test from 'node:test';
import assert from 'node:assert/strict';
import {brokerConnectionIssue,type DemoMarket} from '../src/demoMarket';

test('LIVE configuration failure is explained instead of perpetual connecting',()=>{
  const market={environment:'live',connection_status:'ACCOUNT_ID_REQUIRED'} as DemoMarket;
  assert.equal(brokerConnectionIssue(market),'LIVE 尚未設定 Open API 帳戶 ID');
  assert.equal(brokerConnectionIssue({...market,environment:'demo'}),null);
});
