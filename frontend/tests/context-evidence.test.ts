import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createElement} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {DemoEngine} from '../src/demo';
import {PoolEvidence,CaseEvidence} from '../src/SimilarityEvidence';
import {poolDescription} from '../src/similarityPresentation';

const limits={d5:.25,d1h:.5,dtail:.1,vol_ratio:2};
function pool(){
 const r=new DemoEngine().retrieve('BUY','FIRST','.1');
 return {...r,total:0,cases:[],full_cases:[],five_minute_only_cases:[],rule_status:'NO_RULE_MATCH' as const,
  comparison:{...r.comparison!,mode:'candidate_market' as const,method:'context_contract_v1',basis:'context_rules',
   eligible_rows:20,passed_rows:0,passed_unique:0,thresholds:limits,
   rejections:{event_stage:12,volatility:10},rejection_labels:{event_stage:'目前事件階段不同',volatility:'波動倍率超過容忍'},
   query_event_label:'跌出後收回區間',query_tail_direction:'上行',reason:'有可比較案例，但無案例通過全部條件'}};
}

test('context no-match explains rejected data without calling it missing data or old ranks',()=>{
 const r=pool();const text=poolDescription(r);
 assert.match(text.market,/無符合案例/);
 const html=renderToStaticMarkup(createElement(PoolEvidence,{pool:r}));
 assert.match(html,/跌出後收回區間/);assert.match(html,/事件階段不同/);
 assert.match(html,/20/);assert.match(html,/容忍/);assert.match(html,/不可相加/);
 assert.doesNotMatch(html,/前 15|兩軸相對排名|技術指標＋固定型態|完整三週期/);
 const missing={...r,rule_status:'INSUFFICIENT_DATA' as const,candidate_market_unavailable_reason:'缺少一小時棒'};
 assert.match(poolDescription(missing).market,/資料不足/);
});

test('context case shows actual path gaps and tolerance without invented confidence',()=>{
 const base=new DemoEngine().retrieve('BUY','FIRST','.1').cases[0];
 const item={...base,retrieval_method:'context_contract_v1' as const,path_distance_pct:.12,
  hour_path_distance_pct:.3,tail_path_distance_pct:.04,volatility_ratio:1.4,
  event_label:'跌出後收回區間',query_event_label:'跌出後收回區間',tail_direction:'上行',query_tail_direction:'變動不大',
  context_check:{passed:true,score_max:.6,score_sum:1.8,thresholds:limits}};
 const html=renderToStaticMarkup(createElement(CaseEvidence,{item}));
 assert.match(html,/0.120/);assert.match(html,/0.300/);assert.match(html,/0.040/);assert.match(html,/1.40/);
 assert.match(html,/0.250/);assert.match(html,/最近半小時/);
 assert.doesNotMatch(html,/操作距離|池內排名|另列不排名|相似度60/);
});
