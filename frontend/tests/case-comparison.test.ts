import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createElement} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import CaseComparison,{type CaseComparisonData} from '../src/CaseComparison';

const data:CaseComparisonData={status:'PASSED',label:'有符合條件的案例',reason:'通過試驗條件，不代表完全一樣。',method:'context_contract_v1',side:'BUY',snapshot_id:'abc',query_as_of_utc:1800000000,query_state:{event:'區間內活動',tail_direction:'上行'},counts:{eligible:9,passed:2,displayed:1},cases:[{ref:'案例甲',case_id:'PRIVATE_ID',event:'區間內活動',tail_direction:'上行',similarities:['同方向'],differences:[],metrics:[{key:'d5',label:'五分鐘路徑',actual:'0.12000',tolerance:'0.25000',unit:'%',passed:true}]}],rejections:[]};

test('comparison displays rule distances, tolerance and same-snapshot chart action without outcomes or private IDs',()=>{
 const html=renderToStaticMarkup(createElement(CaseComparison,{comparison:data,snapshotId:'abc'}));
 for(const word of ['有符合條件的案例','BUY','0.12000','0.25000','差距','容忍','對照同一快照 K 線'])assert.ok(html.includes(word),word);
 assert.doesNotMatch(html,/PRIVATE_ID|勝率|獲利率/);
});

test('no-rule-match shows reason counts but never offers a fabricated matching chart',()=>{
 const html=renderToStaticMarkup(createElement(CaseComparison,{comparison:{...data,status:'NO_RULE_MATCH',label:'有資料，但沒有符合案例',cases:[],counts:{eligible:9,passed:0,displayed:0},rejections:[{key:'five_path',label:'五分鐘完整路徑差距超過容忍',count:8}]},snapshotId:'abc'}));
 assert.match(html,/五分鐘完整路徑差距超過容忍/);assert.match(html,/8/);assert.match(html,/不能相加/);
 assert.doesNotMatch(html,/對照同一快照 K 線/);
});

test('unknown distance is not displayed as zero',()=>{
 const next=structuredClone(data);next.cases[0].metrics[0].actual=null;next.cases[0].metrics[0].passed=null;
 const html=renderToStaticMarkup(createElement(CaseComparison,{comparison:next,snapshotId:'abc'}));
 assert.match(html,/資料不足/);assert.doesNotMatch(html,/0\.00000/);
});
