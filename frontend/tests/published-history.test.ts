import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {test} from 'node:test';
import {PublicHistoryStore} from '../src/publicHistory';

const load=(name:string)=>JSON.parse(readFileSync(`public/data/${name}`,'utf8'));

test('published real archive and compact index support point-in-time retrieval',()=>{
  const raw=load('trader-cases.json');
  const index=load('trader-market-index.json');
  const queries=load('synthetic-query-profiles.json');
  assert.equal(raw.cases.length,11902);
  assert.equal(index.cases.length,10887);
  assert.equal(queries.queries.length,361);
  assert.ok(index.cases.every((row:{text?:string})=>row.text?.includes('進場前已收60根5分鐘K線')));
  assert.ok(queries.queries.every((row:{text?:string})=>row.text?.includes('進場前已收60根5分鐘K線')));
  const store=new PublicHistoryStore(raw,index,queries);
  const query=queries.queries[0];
  const rawById=new Map<string,{id:string;available_at:number}>(
    raw.cases.map((row:{id:string;available_at:number})=>[row.id,row] as const));
  const result=store.retrieve('BUY',360);
  assert.equal(result.comparison?.method,'path_indicator_pattern_v1');
  assert.equal(result.comparison?.basis,'synthetic_query_real_history');
  assert.ok((result.full_cases?.length??0)>0);
  assert.ok(result.full_cases!.every(item=>item.source_kind==='trader_history'));
  assert.ok(result.full_cases!.every(item=>item.market_state_text?.includes('進場前已收60根5分鐘K線')));
  assert.ok(result.full_cases!.every(item=>rawById.get(item.id)!.available_at<=query.as_of));
  const detail=store.detail(result.full_cases![0].id,query.as_of);
  assert.equal(detail?.market_path_pct?.length,60);
  assert.equal(detail?.sequence.length,raw.group_sequences[detail!.group].length);
  assert.equal(store.audit().total_gold_records,11902);
});
