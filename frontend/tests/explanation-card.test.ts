import {strict as assert} from 'node:assert';
import {test} from 'node:test';
import {createElement} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import ExplanationCard from '../src/ExplanationCard';
import type {Explanation} from '../src/types';

const card:Explanation={version:1,as_of_utc:'2025-10-02T07:00:00+00:00',origin:'program',status:'invalid_selection',model:'test',sections:[{id:'history',title:'歷史案例',facts:[{id:'history.status',text:'沒有符合案例 <script>fake()</script>',source:'案例檢索',evidence:{status:'no_matches'}}]}]};

test('card exposes source, UTC snapshot and honest fallback without raw HTML',()=>{
  const html=renderToStaticMarkup(createElement(ExplanationCard,{card}));
  assert.match(html,/2025-10-02 07:00:00 UTC/);
  assert.match(html,/模型資料引用無效/);
  assert.match(html,/案例檢索 · 查看依據/);
  assert.match(html,/no_matches/);
  assert.ok(!html.includes('<script>'));
});

test('validated selection is labelled as organization, not generated advice',()=>{
  const html=renderToStaticMarkup(createElement(ExplanationCard,{card:{...card,origin:'model_selection',status:'ok'}}));
  assert.match(html,/模型整理重點 · 程式提供資料/);
  assert.match(html,/重點編排：test/);
  assert.ok(!html.includes('模型資料引用無效'));
});
