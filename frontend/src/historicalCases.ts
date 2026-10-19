/** Read-only, point-in-time public ranker for the explicitly released archive. */
import Decimal from 'decimal.js';
import type {Case,Retrieval,Side} from './types';

export const FIVE=['5m_ma_gap','5m_atr_pct','5m_rsi14','5m_macd_hist','5m_slope','range_position'] as const;
export const HIGH=['15m_ma_gap','15m_atr_pct','15m_rsi14','15m_macd_hist','1h_ma_gap','1h_atr_pct'] as const;
export type HistoricalQuery={cursor:number;as_of:number;tier:'full'|'5m_only';path:number[];indicators:Record<string,number>;pattern:string;text?:string};
export type HistoricalIndexCase={id:string;group:string;side:Side;available_at:number;as_of:number;tier:'full'|'5m_only';path:number[];indicators:Record<string,number>;pattern:string;text?:string};
export type HistoricalRank={case_id:string;group:string;tier:'full'|'5m_only';path_distance_pct:number;path_percentile:number;indicator_percentile:number;indicator_differences:Record<string,number>;pattern_code:string;pattern_match:boolean;text?:string};

function midrank(value:number,sorted:number[]):number{
  let low=0,high=sorted.length;
  while(low<high){const mid=(low+high)>>1;if(sorted[mid]<value)low=mid+1;else high=mid;}
  const left=low;high=sorted.length;
  while(low<high){const mid=(low+high)>>1;if(sorted[mid]<=value)low=mid+1;else high=mid;}
  return (left+(low-left)/2)/sorted.length;
}
function median(values:number[]):number{
  const sorted=[...values].sort((a,b)=>a-b),middle=sorted.length>>1;
  return sorted.length%2?sorted[middle]:(sorted[middle-1]+sorted[middle])/2;
}
function rankTier(cases:HistoricalIndexCase[],query:HistoricalQuery,tier:'full'|'5m_only'):HistoricalRank[]{
  const keys=[...FIVE,...(tier==='full'?HIGH:[])];
  const measured:HistoricalRank[]=[];
  for(const candidate of cases){
    if(candidate.path.length!==60||query.path.length!==60)continue;
    const pathDistance=Math.sqrt(query.path.reduce((sum,value,i)=>sum+(value-candidate.path[i])**2,0)/60);
    const differences:Record<string,number>={};
    for(const key of keys)differences[key]=Math.abs(query.indicators[key]-candidate.indicators[key]);
    if(!Number.isFinite(pathDistance)||keys.some(key=>!Number.isFinite(differences[key])))continue;
    measured.push({case_id:candidate.id,group:candidate.group,tier,
      path_distance_pct:pathDistance,path_percentile:0,indicator_percentile:0,
      indicator_differences:differences,pattern_code:candidate.pattern,pattern_match:candidate.pattern===query.pattern,text:candidate.text});
  }
  if(!measured.length)return [];
  const pathValues=measured.map(row=>row.path_distance_pct).sort((a,b)=>a-b);
  const byFeature=Object.fromEntries(keys.map(key=>[key,measured.map(row=>row.indicator_differences[key]).sort((a,b)=>a-b)])) as Record<string,number[]>;
  for(const row of measured){
    row.path_percentile=midrank(row.path_distance_pct,pathValues);
    row.indicator_percentile=median(keys.map(key=>midrank(row.indicator_differences[key],byFeature[key])));
  }
  measured.sort((a,b)=>
    Math.max(a.path_percentile,a.indicator_percentile)-Math.max(b.path_percentile,b.indicator_percentile)||
    (a.path_percentile+a.indicator_percentile)-(b.path_percentile+b.indicator_percentile)||
    a.case_id.localeCompare(b.case_id));
  return measured;
}
function distinctAndRerank(rows:HistoricalRank[],seen:Set<string>):HistoricalRank[]{
  const distinct:HistoricalRank[]=[];
  for(const row of rows){if(!seen.has(row.group)){seen.add(row.group);distinct.push(row);}}
  const head=distinct.slice(0,15),tail=distinct.slice(15);
  return [...head.filter(row=>row.pattern_match),...head.filter(row=>!row.pattern_match),...tail];
}
export function rankHistoricalCases(cases:HistoricalIndexCase[],query:HistoricalQuery,side:Side){
  if(!['BUY','SELL'].includes(side)||query.path.length!==60||!['full','5m_only'].includes(query.tier))
    return {full:[] as HistoricalRank[],five_minute_only:[] as HistoricalRank[],full_pool:0,five_minute_only_pool:0};
  const eligible=cases.filter(row=>row.side===side&&row.available_at<=query.as_of&&row.as_of<=query.as_of);
  const fullPool=query.tier==='full'?eligible.filter(row=>row.tier==='full'):[];
  const limitedPool=query.tier==='full'?eligible.filter(row=>row.tier==='5m_only'):eligible;
  const seen=new Set<string>();
  const full=distinctAndRerank(rankTier(fullPool,query,'full'),seen);
  const five_minute_only=distinctAndRerank(rankTier(limitedPool,query,'5m_only'),seen);
  return {full,five_minute_only,full_pool:fullPool.length,five_minute_only_pool:limitedPool.length};
}

export function toHistoricalRetrieval(
  ranked:ReturnType<typeof rankHistoricalCases>,query:HistoricalQuery,archive:Case[],
):Retrieval{
  const byId=new Map(archive.map(row=>[row.id,row]));
  const makeRows=(rows:HistoricalRank[]):Case[]=>rows.slice(0,5).flatMap(row=>{
    const original=byId.get(row.case_id);
    if(!original)return [];
    return [{...original,distance:null,candidate_tier:row.tier,
      comparison_basis:'synthetic_query_real_history',
      reference_alignment:'PROJECT_REFERENCE' as const,clock_status:'UNKNOWN' as const,
      path_rank:Number(row.path_percentile.toFixed(4)),path_distance_pct:Number(row.path_distance_pct.toFixed(5)),
      indicator_rank:Number(row.indicator_percentile.toFixed(4)),
      indicator_differences:row.indicator_differences,pattern_code:row.pattern_code,
      market_state_text:row.text,
      pattern_match:row.pattern_match,
      match_reasons:['方向相同','進場前 K 線路徑與指標雙軸近鄰',
        row.pattern_match?'三段走勢型態相同':'三段走勢型態不同'],
      differences:['查詢盤面為合成回放；交易員參考盤面的券商原始時鐘尚未獨立核實'],
    }];
  });
  const full=makeRows(ranked.full),limited=makeRows(ranked.five_minute_only);
  const counts={wins:0,losses:0,flat:0,unknown:0};
  for(const row of ranked.full){
    const raw=byId.get(row.case_id)?.profit;
    try{
      const value=new Decimal(raw??'NaN');
      if(!value.isFinite())counts.unknown++;
      else if(value.gt(0))counts.wins++;
      else if(value.lt(0))counts.losses++;
      else counts.flat++;
    }catch{counts.unknown++;}
  }
  const known=counts.wins+counts.losses+counts.flat,total=ranked.full.length;
  const reason=full.length||limited.length?
    '同方向且查詢前已成熟；路徑與指標近鄰經固定型態重排，足夠相似門檻尚未校準。':
    '此合成回放時點沒有可比較且已成熟的真實歷史案例。';
  return {total,...counts,win_rate:known?(counts.wins/known*100).toFixed(1):null,
    cases:full,full_cases:full,five_minute_only_cases:limited,
    five_minute_only_total:ranked.five_minute_only.length,
    profit_cases:full.filter(row=>new Decimal(row.profit).gt(0)),
    loss_cases:full.filter(row=>new Decimal(row.profit).lt(0)),
    similarity_sufficiency:full.length||limited.length?'UNCALIBRATED':'NO_MATCH',
    comparison:{mode:'candidate_market',alignment_scope:'PROJECT_REFERENCE',
      independent_clock_verified:false,clock_status:'UNKNOWN',method:'path_indicator_pattern_v1',
      basis:'synthetic_query_real_history',market_features_enabled:true,parameters_validated:false,
      query_pattern_code:query.pattern,rerank_window:15,
      query_market_text:query.text,
      full_pool:ranked.full_pool,five_minute_only_pool:ranked.five_minute_only_pool,reason},
    sufficiency:{status:full.length||limited.length?'limited':'insufficient',
      label:full.length||limited.length?'真實歷史盤面近鄰／未校準':'資料不足',
      reasons:[reason],matched_groups:full.length+limited.length,is_success_probability:false},
    limitations:['目前查詢 K 線是合成回放，候選案例來自真實交易員紀錄；兩者來源不同',
      '參考行情依來源時間模型定位，券商原始時鐘尚未獨立核實',
      '歷史結果分布僅供描述；損益沒有參與排名，也不代表這筆交易的獲利機率'],
  };
}
