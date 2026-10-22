import Decimal from 'decimal.js';import type {MarketReply} from './LiveAssistant';
export const asksVolume=(question:string)=>/成交量|交易量|量能|量比|tick\s*量|放量|縮量|量柱/i.test(question);
const prefixes=[['f5','五分鐘',/(?<!十)五分|(?<!\d)5\s*分|5m/i],['f15','十五分鐘',/十五分|15\s*分|15m/i],['f1','一小時',/一小時|1\s*h|小時|60分/i]] as const;
const numeric=(value:string|undefined)=>{try{return value!==undefined&&new Decimal(value).isFinite()&&new Decimal(value).gte(0)?value:null;}catch{return null;}};
export default function LiveVolumeAnalysis({reply:r,question=''}:{reply:MarketReply;question?:string}){
 if(!['CURRENT','FROZEN'].includes(r.market_status))return null;
 const explicit=prefixes.filter(([, ,pattern])=>pattern.test(question));
 const used=new Set(r.sections.flatMap(s=>s.fact_ids.map(id=>id.split('.')[0])));
 const periods=explicit.length?explicit:prefixes.filter(([p])=>used.has(p));
 const rows=(periods.length?periods:prefixes.filter(([p])=>p!=='f15')).flatMap(([p,label])=>{
  const f=r.evidence.find(f=>f.id===p+'.volume');if(!f)return [];
  const v=f.values;return [{label,count:numeric(v[p+'_volume_count']),mean:numeric(v[p+'_volume_mean']),ratio:numeric(v[p+'_volume_ratio']),state:v[p+'_volume_state'],note:v[p+'_volume_note_state']}];
 });
 if(!rows.length)return null;
 return <section className="cw-volume-analysis" aria-label="券商 tick 量分析"><h3>量能 · 券商 tick 量</h3><ul>{rows.map(row=><li key={row.label}><strong>{row.label}</strong><div><p>末根已收棒 <b>{row.count??'未提供'}</b> 次{row.ratio!==null&&<> · 約 <b>{new Decimal(row.ratio).toSignificantDigits(3).toString()}</b> 倍均量</>}</p><p className="cw-volume-state">{row.ratio!==null?row.state:row.note||'量資料不足，暫不計算量比'}</p></div></li>)}</ul><details><summary>均量與量的定義</summary>{rows.map(row=><p key={row.label}>{row.label}前20根已收棒平均：{row.mean??'未提供'} 次。</p>)}<p>此處是券商報價更新次數，用來觀察活躍度；不是成交手數或全球成交量。即時形成棒的本機接收計數另列在看盤圖，不混入此分析。</p></details></section>;
}
