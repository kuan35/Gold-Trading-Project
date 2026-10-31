import test from 'node:test';import assert from 'node:assert/strict';import {createElement} from 'react';import {renderToStaticMarkup} from 'react-dom/server';
import HoldingObservation from '../src/HoldingObservation';

test('reference movement is a collapsed observation, not the original trade result',()=>{
 const html=renderToStaticMarkup(createElement(HoldingObservation,{observation:{status:'PARTIAL',reason:'有缺口',bars_used:3,observed_mae_pct:'5',observed_mfe_pct:'10',reference_return_pct:'4'}}));
 assert.match(html,/<details class="holding-observation">/);assert.doesNotMatch(html,/<details[^>]*open=/);
 for(const text of ['已知最大逆向','5.000%','已知最大順向','10.000%','觀察段收尾變動','4.000%','時間間隔','不是原單實際損益'])assert.ok(html.includes(text),text);
});

test('no completed holding bar does not display a fake zero excursion',()=>{
 const html=renderToStaticMarkup(createElement(HoldingObservation,{observation:{status:'INSUFFICIENT',reason:'進出場之間沒有完整收盤棒',bars_used:0,observed_mae_pct:null,observed_mfe_pct:null,reference_return_pct:null}}));
 assert.match(html,/沒有完整收盤棒/);assert.doesNotMatch(html,/0\.000%|<dl/);
});
