import type {SeriesMarker,UTCTimestamp} from 'lightweight-charts';
import type {Marker} from './types';

/** Arrows identify time/side outside the candle; focus lines identify price. */
export function displayMarker(m:Marker,focusIds:string[]):SeriesMarker<UTCTimestamp> {
  const up=m.shape==='arrowUp'||(m.shape==='circle'&&m.position==='belowBar');
  const label=m.action==='CLOSE'?'出場':m.action==='FIRST'?'首筆':m.action==='ADD'?'加單':m.text;
  return {id:m.id,time:m.time as UTCTimestamp,color:m.color,shape:m.shape==='circle'?'circle':up?'arrowUp':'arrowDown',
    position:up?'belowBar':'aboveBar',size:focusIds.includes(m.id||'')?1.15:1,
    text:m.price?`${label} ${m.price}`:m.text};
}
