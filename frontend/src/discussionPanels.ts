import type {MarketReply} from './LiveAssistant';
import type {Side} from './types';
export type TrendSignal={text:string;period:'5m'|'15m'|'1h';factId:string};
export function trendSignals(reply:MarketReply,side:Side|null){
 const support:TrendSignal[]=[],against:TrendSignal[]=[],observations:TrendSignal[]=[];
 if(!['CURRENT','FROZEN'].includes(reply.market_status))return {support,against,observations};
 for(const [prefix,period] of [['f5','5m'],['f15','15m'],['f1','1h']] as const){
  const fact=reply.evidence.find(f=>f.id===prefix+'.trend'),bias=fact?.values[prefix+'_bias'];
  if(!fact||!bias)continue;
  const signal={text:bias,period,factId:fact.id};
  const bullish=/偏多/.test(bias)&&!/偏空/.test(bias),bearish=/偏空/.test(bias)&&!/偏多/.test(bias);
  if(!side||(!bullish&&!bearish))observations.push(signal);
  else if((side==='BUY'&&bullish)||(side==='SELL'&&bearish))support.push(signal);
  else against.push(signal);
 }
 return {support,against,observations};
}
