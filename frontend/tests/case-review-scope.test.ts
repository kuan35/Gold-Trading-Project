import test from 'node:test';import assert from 'node:assert/strict';import {createElement} from 'react';import {renderToStaticMarkup} from 'react-dom/server';
import {caseReviewScope,matchingCaseReview,casePreviewUrl} from '../src/caseReviewScope';
import CaseReviewPanel from '../src/CaseReviewPanel';

test('review identity binds both snapshot and selected case, with legacy all-case support',()=>{
 assert.notEqual(caseReviewScope('s','案例甲'),caseReviewScope('s','案例乙'));
 assert.equal(matchingCaseReview({snapshot_id:'s',case_ref:'案例乙'},'s','案例乙'),true);
 for(const value of [{snapshot_id:'old',case_ref:'案例乙'},{snapshot_id:'s',case_ref:'案例甲'},{snapshot_id:'s'}])assert.equal(matchingCaseReview(value,'s','案例乙'),false);
 assert.equal(matchingCaseReview({snapshot_id:'s',case_ref:null},'s'),true);
 assert.match(casePreviewUrl('s/1','案例乙'),/s%2F1\/case-preview\?case_ref=/);
});

test('selected panel explicitly names its case rather than implying all five cases',()=>{
 const html=renderToStaticMarkup(createElement(CaseReviewPanel,{snapshotId:'s',caseRef:'案例乙'}));
 assert.match(html,/讓助手分析案例乙/);assert.match(html,/只分析目前選取的案例乙/);
 assert.doesNotMatch(html,/最多五例|分析這次檢索出的案例/);
});
