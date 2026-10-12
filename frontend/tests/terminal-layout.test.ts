import {test} from 'node:test';
import assert from 'node:assert/strict';
import {panelWidth,resizeWidth,DEFAULT_WIDTH,MIN_WIDTH,MAX_WIDTH} from '../src/terminalLayout';

test('corrupt or unsupported saved layout falls back to a usable order ticket',()=>{
  for(const value of [null,'','NaN','Infinity','{}','-20']) assert.equal(panelWidth(value),DEFAULT_WIDTH);
  assert.equal(panelWidth('370'),370);
  assert.equal(panelWidth('99999'),MAX_WIDTH);
});

test('dragging keeps the order ticket within its usable width',()=>{
  assert.equal(resizeWidth(336,1000),MIN_WIDTH);
  assert.equal(resizeWidth(336,-1000),MAX_WIDTH);
  assert.equal(resizeWidth(336,-24),360);
});
