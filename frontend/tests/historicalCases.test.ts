import assert from 'node:assert/strict';
import {test} from 'node:test';
import {rankHistoricalCases,toHistoricalRetrieval,type HistoricalIndexCase,type HistoricalQuery} from '../src/historicalCases';

const indicators={
  '5m_ma_gap':0,'5m_atr_pct':0.5,'5m_rsi14':50,'5m_macd_hist':0,
  '5m_slope':0,'range_position':0.5,'15m_ma_gap':0,'15m_atr_pct':0.5,
  '15m_rsi14':50,'15m_macd_hist':0,'1h_ma_gap':0,'1h_atr_pct':0.5,
};
const query:HistoricalQuery={cursor:360,as_of:1000,tier:'full',
  path:Array(60).fill(0),indicators,pattern:'UDU'};
function item(id:string,changes:Partial<HistoricalIndexCase>={}):HistoricalIndexCase{
  return {id,group:id,side:'BUY',available_at:900,as_of:800,tier:'full',
    path:Array(60).fill(0),indicators,pattern:'UDU',...changes};
}

test('historical rank excludes future and opposite cases, deduplicates groups, ignores outcome',()=>{
  const cases=[item('a'),item('a2',{group:'a'}),item('b',{pattern:'UUU'}),
    item('future',{available_at:1100}),item('sell',{side:'SELL'})];
  const ranked=rankHistoricalCases(cases,query,'BUY');
  assert.deepEqual(ranked.full.map(row=>row.case_id),['a','b']);
  assert.equal(ranked.full_pool,3);
  assert.equal(ranked.full[0].pattern_match,true);
});

test('exact pattern only reranks the first fifteen distinct numeric neighbors',()=>{
  const cases=Array.from({length:20},(_,i)=>item(String(i).padStart(2,'0'),{
    path:Array(60).fill(i/100),pattern:i===16?'UDU':'UUU'}));
  const ranked=rankHistoricalCases(cases,query,'BUY');
  assert.equal(ranked.full[0].case_id,'00');
  assert.equal(ranked.full.find(row=>row.case_id==='16')?.pattern_match,true);
  assert.equal(ranked.full[16].case_id,'16');
});

test('five-minute-only query does not claim higher-frame matches',()=>{
  const q={...query,tier:'5m_only' as const};
  const ranked=rankHistoricalCases([item('full'),item('limited',{tier:'5m_only'})],q,'BUY');
  assert.equal(ranked.full.length,0);
  assert.equal(ranked.five_minute_only.length,2);
});

test('identical numerical scores use stable case ID before group deduplication',()=>{
  const tied=[item('z',{group:'same',tier:'5m_only'}),item('a',{group:'same',tier:'5m_only'})];
  const ranked=rankHistoricalCases(tied,query,'BUY');
  assert.deepEqual(ranked.five_minute_only.map(row=>row.case_id),['a']);
});

test('real case retrieval shows outcome only after ranking and labels synthetic query',()=>{
  const archive=[{id:'a',group:'a',side:'BUY',action:'FIRST',lot:'0.1',entry:'100',exit:'101',
    opened_at:'2020-01-01 00:00:00',closed_at:'2020-01-01 01:00:00',available_at:900,
    profit:'10',label:'首筆',currency:'USD',source_kind:'trader_history',time_alignment:'unknown',
    behavior:'NO_OBSERVED_POSITION',sequence:[],match_reasons:[],differences:[],distance:null}];
  const index=[item('a')];
  const ranked=rankHistoricalCases(index,query,'BUY');
  const result=toHistoricalRetrieval(ranked,query,archive);
  assert.equal(result.comparison?.method,'path_indicator_pattern_v1');
  assert.equal(result.comparison?.basis,'synthetic_query_real_history');
  assert.equal(result.full_cases?.[0].source_kind,'trader_history');
  assert.equal(result.wins,1);
  archive[0].profit='-1000';
  const changed=toHistoricalRetrieval(rankHistoricalCases(index,query,'BUY'),query,archive);
  assert.equal(changed.full_cases?.[0].id,result.full_cases?.[0].id);
  assert.equal(changed.wins,0);
});
