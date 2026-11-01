export type GoldRelation={title:string;mechanism:string;bullish:string;bearish:string;unknown:string;sources:string[]};
export type MacroEvent={id:string;title:string;topic:string;date:string;scheduled_at_utc:string|null;timing_precision:string;status:string;freshness:string;fetched_at_utc:string;source_url:string;actual:string|null;consensus:string|null;previous:string|null;gold_relation:GoldRelation};
export type MacroNews={id:string;title:string;summary:string;source_url:string;published_at_utc:string;fetched_at_utc:string;freshness:string;gold_relation:GoldRelation};
export type MacroSnapshot={status:string;snapshot_id:string;as_of_utc:string;coverage:string;events:MacroEvent[];news:MacroNews[];sources:{id:string;url:string;status:string;fetched_at_utc:string|null;reason?:string|null}[];consensus_status:string;actual_values_status:string};
export function safeSourceUrl(value:string):string|undefined{try{const u=new URL(value);return u.protocol==='https:'&&!u.username&&!u.password&&['www.federalreserve.gov','www.bls.gov','www.bea.gov','apps.bea.gov','www.gold.org','help.ctrader.com'].includes(u.hostname)&&(!u.port||u.port==='443')?u.href:undefined;}catch{return undefined;}}
export const taiwanTime=(value:string)=>Number.isFinite(Date.parse(value))?new Date(value).toLocaleString('zh-TW',{timeZone:'Asia/Taipei',hour12:false})+' 台灣時間':'時間未確認';
export const eventTimeLabel=(event:MacroEvent)=>event.scheduled_at_utc?taiwanTime(event.scheduled_at_utc):event.date+' 美東日期 · 時刻待確認';
export function eventProximity(event:MacroEvent,now=Date.now()):string{
 if(event.status==='CANCELLED')return '已取消';
 if(event.freshness!=='CURRENT'||now-Date.parse(event.fetched_at_utc)>=900_000)return '上次快取排程，待重新核對';
 if(!event.scheduled_at_utc)return '發布時刻待確認';
 const delta=Date.parse(event.scheduled_at_utc)-now;if(!Number.isFinite(delta))return '發布時刻待確認';
 if(delta<=0)return '已到排程時間，公布結果尚未讀取';
 return delta<=3_600_000?`距排程約 ${Math.ceil(delta/60_000)} 分鐘`:`距排程約 ${Math.ceil(delta/3_600_000)} 小時`;
}
export function requestsMacroContext(text:string):boolean{
 return /\b(?:CPI|PCE|GDP|PPI|FOMC)\b|非農|聯準會|總經|經濟事件|經濟數據|利率|升息|降息|消息|新聞|公告|發言|聲明|行事曆|日曆/i.test(text);
}
export function goldQuestionKind(text:string):'knowledge'|'calendar'|'news'|null{
 if(/(?:買進|買入|賣出|下單|做多|做空).*\d|(?:修改|改成|設為|設定).*(?:手數|停損|停利|限價)|(?:停損|停利|手數|限價)\s*\d|我想.*(?:做多|做空|買|賣)|如果.*(?:做多|做空)/i.test(text))return null;
 if(!/黃金|CPI|PCE|GDP|PPI|非農|聯準會|FOMC|總經|經濟事件|利率|升息|降息|保證金|槓桿|限價單|市價單|停損|停利|tick|成交量|消息|新聞|行事曆/i.test(text))return null;
 if(/今天|今晚|本週|這週|下週|最近|最新|目前/.test(text)&&/新聞|消息|公告|發言|聲明/.test(text))return 'news';
 if(/盤面|走勢|報價|K線/i.test(text)&&!/CPI|PCE|GDP|PPI|非農|聯準會|FOMC|事件|新聞|消息/i.test(text))return null;
 if(/是什麼|什麼是|意思|為什麼|如何影響|怎麼影響|有何關聯|有什麼關係|差別|知識|解釋/.test(text))return 'knowledge';
 if(/新聞|消息|公告|發言|聲明/.test(text))return 'news';
 if(/事件|行事曆|日曆|公布|發布|今天|今晚|本週|這週|下次|下週|何時|什麼時候/.test(text))return 'calendar';
 return /CPI|PCE|GDP|PPI|非農|FOMC|聯準會|利率|升息|降息|保證金|槓桿|限價單|市價單|停損|停利/i.test(text)?'knowledge':null;
}
