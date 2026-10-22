import {test} from 'node:test';import assert from 'node:assert/strict';
import {savedChatHeight} from '../src/chatSize';
test('saved height restores only a bounded integer and corrupt settings use automatic sizing',()=>{
 assert.equal(savedChatHeight('480'),480);for(const value of [null,'','null','{}','Infinity','210.5','-400','200','1001'])assert.equal(savedChatHeight(value),null);
});
