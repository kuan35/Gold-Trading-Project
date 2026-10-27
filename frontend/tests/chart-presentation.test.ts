import {test} from 'node:test';
import assert from 'node:assert/strict';
import {renderToStaticMarkup} from 'react-dom/server';
import {createElement} from 'react';
import {displayMarker} from '../src/chartMarkers';
import MarketDetails from '../src/MarketDetails';
import type {Marker,Technical} from '../src/types';

test('arrows sit outside candles and keep action and executed price in label',()=>{
  const base:Marker={time:1,position:'belowBar',shape:'arrowUp',color:'#44c4b0',text:'',price:'3843.12',action:'FIRST',id:'one'};
  const buy=displayMarker(base,['one']);
  assert.equal(buy.shape,'arrowUp');assert.equal(buy.position,'belowBar');
  assert(buy.text?.includes('首筆 3843.12'));
  assert(!('price' in buy));
  const sell=displayMarker({...base,position:'aboveBar',shape:'arrowDown',action:'CLOSE'},[]);
  assert.equal(sell.position,'aboveBar');assert.equal(sell.shape,'arrowDown');
  assert(sell.text?.includes('出場'));
  const boundary=displayMarker({...base,time:600,position:'aboveBar',shape:'circle',text:'歷史後續起點',price:undefined,action:undefined},[]);
  assert.equal(boundary.shape,'circle');
  assert.equal(boundary.position,'aboveBar');
});

test('market details renders generated direction, reasons and each plain-language reading',()=>{
  const a:Technical={interval:'5m',count:60,last_closed_at:18000,rsi14:'51',macd_line:'-3',macd_signal:'-5',macd_histogram:'2',atr14:'6',boll_lower:'3800',boll_middle:'3834',boll_upper:'3850',source_volume_ratio:'.9',definitions:'方法',
    levels:{status:'candidate',lookback_count:60,method:'轉折',support:[],resistance:[]},
    reading:{bias:'bearish_rebound',label:'空方結構中的反彈',reasons:['價格仍低於MA60','動能接近平衡','負軸但高於訊號線'],indicators:{rsi:'RSI解讀',macd:'MACD解讀',atr:'ATR解讀',bollinger:'布林解讀',volume:'來源量解讀'},method:'規則'}};
  const html=renderToStaticMarkup(createElement(MarketDetails,{analysis:a}));
  for(const text of ['空方結構中的反彈','價格仍低於MA60','RSI解讀','MACD解讀','ATR解讀','布林解讀','來源量解讀'])assert(html.includes(text));
});
