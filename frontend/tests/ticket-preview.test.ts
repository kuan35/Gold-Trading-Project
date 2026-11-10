import test from 'node:test';import assert from 'node:assert/strict';
import {createElement} from 'react';import {renderToStaticMarkup} from 'react-dom/server';
import {TicketLevel,TicketPreviewNote} from '../src/TicketPreview';
test('SL/TP display keeps signed USD and price return, never labels it margin ROI',()=>{
 const html=renderToStaticMarkup(createElement(TicketLevel,{level:{status:'AVAILABLE',reason:null,pnl_usd:'-500.00',price_return_pct:'-0.2500'}}));
 assert.match(html,/-500.00 USD/);assert.match(html,/-0.2500%/);assert.match(html,/價格報酬率/);assert.doesNotMatch(html,/保證金報酬率/);
 const invalid=renderToStaticMarkup(createElement(TicketLevel,{level:{status:'INVALID_SIDE',reason:'停損方向錯誤',pnl_usd:null,price_return_pct:null}}));
 assert.match(invalid,/停損方向錯誤/);assert.doesNotMatch(invalid,/0.00/);
});

test('margin ROI is separately labeled and the 1:200 assumption stays visible',()=>{
 const html=renderToStaticMarkup(createElement(TicketLevel,{level:{status:'AVAILABLE',reason:null,pnl_usd:'-500.00',price_return_pct:'-0.2500',margin_roi_pct:'-50.0000'}}));
 assert.match(html,/價格報酬率 -0.2500%/);assert.match(html,/預估保證金報酬率 -50.0000%/);
 const note=renderToStaticMarkup(createElement(TicketPreviewNote,{preview:{pending:false,error:'',data:{status:'AVAILABLE',reason:null,entry_price:'4000',quantity_oz:'50',sl:null,tp:null,quote_time_utc:null,basis:'未扣交易成本',margin:{source:'LEVERAGE_ESTIMATE',amount_usd:'1000.00',leverage:'200',reason:'假設槓桿'},conditional_on_fill:true}}}));
 assert.match(note,/1:200 試算/);assert.match(note,/1000.00 USD/);assert.match(note,/限價單假設已成交/);
 const broker=renderToStaticMarkup(createElement(TicketPreviewNote,{preview:{pending:false,error:'',data:{status:'AVAILABLE',reason:null,entry_price:'4000',quantity_oz:'50',sl:null,tp:null,quote_time_utc:null,basis:'未扣交易成本',margin:{source:'BROKER_EXPECTED',amount_usd:'2000.00',leverage:null,reason:'券商預估'}}}}));
 assert.match(broker,/券商預估/);assert.doesNotMatch(broker,/1:200/);
});
test('background quote refresh retains the preview structure instead of collapsing it',()=>{
 const data={status:'AVAILABLE',reason:null,entry_price:'4000',quantity_oz:'50',sl:null,tp:null,quote_time_utc:null,basis:'未扣交易成本',account_zero:{status:'AVAILABLE',reason:null,zero_bid_price:'3800.20',direction:'DOWN' as const,basis:'固定部位情境'}};
 const idle=renderToStaticMarkup(createElement(TicketPreviewNote,{preview:{pending:false,error:'',data}}));
 const updating=renderToStaticMarkup(createElement(TicketPreviewNote,{preview:{pending:true,error:'',data}}));
 assert.match(updating,/3800.20/);assert.match(updating,/上次試算/);
 const tags=(s:string)=>(s.match(/<\/?(?:section|details|p|strong|summary)\b/g)??[]).join('');
 assert.equal(tags(idle),tags(updating));
});
