import type {CaseComparisonData} from './CaseComparison';
const missing:Record<string,string>={SOURCE_UNAVAILABLE:'目前tick量來源尚未就緒。',SOURCE_MISMATCH:'目前與歷史tick量來源不同，暫不可比較。',QUERY_VOLUME_UNAVAILABLE:'目前沒有可比較的原生tick量。',GAPPED_BASELINE:'前20根tick量基準含缺棒。',INSUFFICIENT_HISTORY:'不足完整21根已收五分棒的tick資料。',ZERO_BASELINE:'前20根tick均量為零，無法計算相對量。',ZERO_TICK_RATIO:'末根tick量為零，暫無法比較倍率。',STALE_VOLUME:'最新已收棒的tick量已過期。'};
export function noCaseReasons(c:CaseComparisonData):string[]{
 if(c.status==='PASSED')return [];
 const reasons:string[]=[];const reason=c.tick_volume?.query_reason;
 if(reason)reasons.push(missing[reason]??c.reason??'目前所需資料不足，無法完成比較。');
 const rows=c.rejections.filter(r=>Number.isFinite(r.count)&&r.count>0).sort((a,b)=>b.count-a.count||a.key.localeCompare(b.key)).slice(0,3);
 reasons.push(...rows.map(r=>`${r.label}：${r.count}筆觀察列`));
 return reasons.length?reasons:[c.reason||'本次所需盤面資料尚未齊全。'];
}
export default function NoCaseReasons({comparison:c}:{comparison:CaseComparisonData}){
 if(c.status==='PASSED')return null;
 return <section className="cw-no-case" aria-label="無案例原因"><h3>{c.label}</h3><strong>{c.status==='INSUFFICIENT_DATA'?'本次資料不足':'主要未通過原因'}</strong><ul>{noCaseReasons(c).map((text,i)=><li key={i}>{text}</li>)}</ul></section>;
}
