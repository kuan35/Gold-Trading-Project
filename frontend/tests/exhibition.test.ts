import test from 'node:test';import assert from 'node:assert/strict';import React from 'react';import {renderToStaticMarkup} from 'react-dom/server';
import TradeResult from '../src/TradeResult';import CaseReviewPanel from '../src/CaseReviewPanel';import LiveReadOnlyPanel from '../src/LiveReadOnlyPanel';
import Chart from '../src/Chart';
test('historical price return is separate from capital ROI and source prices remain visible',()=>{
 const html=renderToStaticMarkup(React.createElement(TradeResult,{result:{status:'AVAILABLE',entry_price:'2000',exit_price:'1990',move_per_oz:'10',price_return_pct:'0.5',margin_roi_pct:null,reason:'before fees'}}));
 assert.match(html,/2000/);assert.match(html,/1990/);assert.match(html,/0.5000%/);assert.match(html,/缺單筆資金基準/);assert.match(html,/價格報酬率（未扣交易成本）/);
});
test('case model defaults to automatic text analysis; LIVE account only mounts after explicit open',()=>{
 const html=renderToStaticMarkup(React.createElement(CaseReviewPanel,{snapshotId:'safe'}));
 assert.doesNotMatch(html,/type="checkbox"/);assert.match(html,/預覽K線圖/);assert.match(html,/分析歷史案例/);
 assert.match(html,/思考程度/);
 const live=renderToStaticMarkup(React.createElement(LiveReadOnlyPanel,{light:false}));
 assert.match(live,/LIVE真實帳戶（唯讀）/);assert.doesNotMatch(live,/<table|確認送出|平倉草稿/);
});
test('execution hover result is an on-chart output, without changing candle data',()=>{
 const bars=[{time:300,open:1,high:2,low:1,close:2}];
 const html=renderToStaticMarkup(React.createElement(Chart,{bars,light:false,hoverLabel:'平倉參考 · 價格報酬率（未扣交易成本） 0.5%'}));
 assert.match(html,/<output class="trade-hover-label">/);assert.match(html,/0.5%/);assert.equal(bars[0].close,2);
});
