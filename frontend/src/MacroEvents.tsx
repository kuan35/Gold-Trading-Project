import {useEffect,useState} from 'react';import {api} from './api';
import {safeSourceUrl,taiwanTime,eventTimeLabel,eventProximity,type GoldRelation,type MacroSnapshot} from './macroEventModel';
export function Source({url,label='資料來源'}:{url:string;label?:string}){const href=safeSourceUrl(url);return href?<a href={href} target="_blank" rel="noopener noreferrer">{label} ↗</a>:null;}
export function GoldInfluence({relation:r}:{relation:GoldRelation}){
 return <section className="macro-influence" aria-label={r.title+'與黃金的情境關聯'}><dl><div><dt>影響機制</dt><dd>{r.mechanism}</dd></div><div className="macro-bull"><dt>可能偏多的情境</dt><dd>{r.bullish}</dd></div><div className="macro-bear"><dt>可能偏空的情境</dt><dd>{r.bearish}</dd></div><div><dt>目前未知</dt><dd>{r.unknown}</dd></div></dl><div className="macro-sources">{r.sources.map((url,i)=><Source key={url} url={url} label={i===0?'關聯性依據':'政策資料'}/>)}</div></section>;
}
export function MacroEvents({snapshot:s}:{snapshot:MacroSnapshot}){
 return <section className="macro-events" aria-label="官方事件與黃金多空情境"><header><h3>事件與黃金的關聯</h3><small>{taiwanTime(s.as_of_utc)}</small></header>
  {s.status!=='AVAILABLE'&&<p role="status">部分來源暫不可用或已過期，以下僅列已取得的資料。</p>}
  {!s.events.length&&<p>目前沒有取得可列出的事件，不代表沒有重大事件。</p>}
  {s.events.slice(0,6).map((e,i)=><details className="macro-event" key={e.id} open={i===0}><summary><strong>{e.gold_relation.title}</strong><span>{eventTimeLabel(e)}</span><small>{e.status==='CANCELLED'?'已取消':e.freshness==='CURRENT'?'官方排程':'快取排程'}</small></summary><p>{e.title}</p><p className="fine">實際值：未讀取 · 市場共識：尚未提供 · 前值：未讀取</p><GoldInfluence relation={e.gold_relation}/><Source url={e.source_url} label="核對官方排程"/><small className="macro-fetched">取得時間：{taiwanTime(e.fetched_at_utc)}</small></details>)}
  {!!s.news.length&&<details className="macro-news"><summary>近期官方公告 · {s.news.length} 則</summary>{s.news.map(n=><article key={n.id}><h4>{n.title}</h4><small>{taiwanTime(n.published_at_utc)} · {n.freshness==='CURRENT'?'已取得官方摘要':'快取摘要'}</small><p>{n.summary}</p><p className="fine">僅有標題與摘要，未判定本次措辭偏鷹或偏鴿。</p><GoldInfluence relation={n.gold_relation}/><Source url={n.source_url} label="閱讀官方原文"/></article>)}</details>}
  <details className="macro-coverage"><summary>來源狀態與覆蓋範圍</summary><p>{s.coverage}</p>{s.sources.map(v=><p key={v.id}><Source url={v.url} label={v.id}/>：{({CURRENT:'已核對',STALE:'舊快取',UNAVAILABLE:'暫不可用',INVALID:'格式未通過'} as Record<string,string>)[v.status]??v.status}{v.reason?' · '+v.reason:''}{v.fetched_at_utc?' · '+taiwanTime(v.fetched_at_utc):''}</p>)}</details>
 </section>;
}
export function MacroCalendarBar({active=true}:{active?:boolean}){
 const [snapshot,setSnapshot]=useState<MacroSnapshot|null>(null),[error,setError]=useState(''),[cycle,setCycle]=useState(0),[now,setNow]=useState(Date.now());
 useEffect(()=>{if(!active||import.meta.env?.MODE==='pages')return;let alive=true;void api<MacroSnapshot>('/assistant/macro-calendar').then(value=>{if(alive){setSnapshot(value);setError('');}}).catch(()=>{if(alive)setError('無法更新官方事件，請稍後重試。');});const timer=window.setInterval(()=>setCycle(v=>v+1),900_000);return()=>{alive=false;window.clearInterval(timer);};},[active,cycle]);
 useEffect(()=>{if(!active)return;const timer=window.setInterval(()=>setNow(Date.now()),30_000);return()=>window.clearInterval(timer);},[active]);
 if(import.meta.env?.MODE==='pages')return <div className="macro-bar">官方事件與知識工具需啟動本機後端。</div>;
 const next=snapshot?.events.find(e=>e.status==='SCHEDULED'&&(e.scheduled_at_utc?Date.parse(e.scheduled_at_utc)>now:true));
 return <details className="macro-bar"><summary><strong>黃金事件</strong><span>{next?next.gold_relation.title:snapshot?'尚無已取得的未來排程':'正在查詢官方行事曆…'}</span>{next&&<small>{error?'時程待更新':eventProximity(next,now)}</small>}<span className="macro-link-label">看多空關聯</span></summary><button type="button" onClick={()=>setCycle(v=>v+1)}>更新來源</button>{error&&<p role="alert">{error}</p>}{snapshot&&<MacroEvents snapshot={snapshot}/>}</details>;
}
