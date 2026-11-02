import type {MarketReply} from './LiveAssistant';
import type {ArchiveTurn} from './deskConversations';
import {analysisLabel} from './assistantProvider';import {selectionLabel} from './modelSettings';
import {trendSignals} from './discussionPanels';
import {validAnalysisRef} from './analysisHistory';

type ConversationTurn={question:string;at?:string;record?:ArchiveTurn;note?:string;noteImportant?:boolean;error?:string;reply?:MarketReply};
const shown=(value:unknown)=>value===null||value===undefined?'未提供':String(value);
const factText=(fact:MarketReply['evidence'][number])=>fact.text.replace(/\{\{([a-z0-9_]+)\}\}/g,(_,key)=>fact.values[key]??'資料不足');

/** Text plus an opaque read-only analysis reference; never serialize order authority. */
export function archiveTurn(turn:ConversationTurn):ArchiveTurn{
 if(turn.record)return turn.record;
 const r=turn.reply,parts:string[]=[];
 if(turn.note&&(turn.noteImportant||!r))parts.push(turn.note);
 if(r){
  parts.push([analysisLabel(r.provider),r.model?selectionLabel(r.model,r.requested_effort):null].filter(Boolean).join(' · '));
  if(!['CURRENT','FROZEN'].includes(r.market_status)&&r.message)parts.push(r.message);
  parts.push(...r.sections.map(s=>`${s.title}\n${s.text}`));
  const c=r.case_comparison;
  if(c){
   const signals=trendSignals(r,c.side==='BUY'||c.side==='SELL'?c.side:null);
   for(const [name,rows] of [['支持訊號',signals.support],['相反訊號',signals.against]] as const)if(rows.length)parts.push(name+'\n'+rows.map(s=>`${s.period}：${s.text}`).join('\n'));
   parts.push(`${c.label} · ${c.side}\n${c.reason}\n合格觀察列 ${shown(c.counts.eligible)}；通過操作群 ${shown(c.counts.passed)}；展示 ${c.counts.displayed} 組。`);
   for(const item of c.cases){
    const lines=[`${item.ref} · ${item.event} · 末段${item.tail_direction}`];
    if(item.representative){const p=item.representative;lines.push(`代表單筆：${p.side}／${p.action}；${shown(p.lot)} 手；原報表結果 ${shown(p.profit)} ${p.currency_stated?shown(p.currency):'幣別未載'}。`);}
    if(item.similarities.length)lines.push('相同處：'+item.similarities.join('；'));
    if(item.differences.length)lines.push('差異：'+item.differences.join('；'));
    lines.push(...item.metrics.map(m=>`${m.label}：實際差距 ${shown(m.actual)} ${m.unit}；容忍 ${shown(m.tolerance)} ${m.unit}；${m.passed===null?'資料不足':m.passed?'符合':'需核對'}`));
    if(item.tick_activity){const t=item.tick_activity;lines.push(`tick量比：目前 ${t.query_relative}／歷史 ${t.case_relative}；差距 ${t.multiplier} 倍。`);}
    parts.push(lines.join('\n'));
   }
   if(c.tick_volume?.enabled)parts.push(`目前tick量比：${shown(c.tick_volume.query_relative)}；容忍 ${shown(c.tick_volume.limit)} 倍；狀態 ${shown(c.tick_volume.query_status)}${c.tick_volume.query_reason?'／'+c.tick_volume.query_reason:''}。`);
   if(c.rejections.length)parts.push('未通過原因\n'+c.rejections.map(v=>`${v.label}：${v.count} 列`).join('\n'));
   if(c.distribution){const d=c.distribution;parts.push(`${d.basis}：${shown(d.total)} 群；獲利 ${shown(d.wins)}／虧損 ${shown(d.losses)}／持平 ${shown(d.flat)}／未知 ${shown(d.unknown)}。`);}
  }
  const outcome=r.outcome_analysis;
  if(outcome){
   const risk=outcome.draft_risk;
   parts.push(risk.status==='AVAILABLE'?`分析時草稿風險：${shown(risk.side)} ${shown(risk.lot)} 手；擬進場 ${shown(risk.entry_price)}；停損 ${shown(risk.stop_price)}；停損名目損失 ${shown(risk.stop_loss_usd)} USD。${risk.conditional_on_fill?'假設限價已成交。':''}`:`分析時草稿風險：${risk.reason}`);
   for(const item of outcome.cases)for(const minutes of [5,30,60]){
    const h=item.horizons[String(minutes)],s=item.scenarios[String(minutes)];if(!h)continue;
    parts.push(h.status==='AVAILABLE'?`${item.ref} · 後續 ${minutes} 分鐘（歷史觀察）：期末變動 ${shown(h.change_pct)}%；途中最大逆向 ${shown(h.mae_pct)}%；途中最大順向 ${shown(h.mfe_pct)}%。`:`${item.ref} · 後續 ${minutes} 分鐘：${h.reason}`);
    if(s)parts.push(s.status==='AVAILABLE'?`原草稿情境損失 ${shown(s.mae_loss_usd)} USD；期末損益 ${shown(s.end_pnl_usd)} USD；最大順向情境 ${shown(s.mfe_profit_usd)} USD。${s.touch_label??''}${s.gap_at_first_touch?' 發生跳空，不能假設停損價成交。':''}`:`情境資料：${s.reason??s.status}`);
   }
  }
  if(r.evidence.length)parts.push('詳細數據\n'+r.evidence.map(factText).join('\n'));
  const macro=r.macro_context;
  if(macro){
   parts.push('消息範圍：'+macro.coverage+'；取得快照 '+macro.as_of_utc);
   for(const e of macro.events){const g=e.gold_relation;parts.push(`${e.title} · ${e.scheduled_at_utc??e.date+'（時間待確認）'} · ${e.status}／${e.freshness}\n影響機制：${g.mechanism}\n可能偏多：${g.bullish}\n可能偏空：${g.bearish}\n未知：${g.unknown}\n來源：${e.source_url}`);}
   for(const n of macro.news){const g=n.gold_relation;parts.push(`官方公告：${n.title}\n${n.summary}\n發布：${n.published_at_utc} · 取得：${n.fetched_at_utc} · ${n.freshness}\n影響機制：${g.mechanism}\n可能偏多：${g.bullish}\n可能偏空：${g.bearish}\n未知：${g.unknown}\n來源：${n.source_url}`);}
  }
  if(r.gold_relation){const g=r.gold_relation;parts.push(`影響機制：${g.mechanism}\n可能偏多：${g.bullish}\n可能偏空：${g.bearish}\n未知：${g.unknown}`);}
  if(r.knowledge_sources?.length)parts.push('知識來源：'+r.knowledge_sources.join('\n'));
 }
 if(turn.error)parts.push(turn.error);
 if(r?.analysis_history_error)parts.push(r.analysis_history_error);
 return {question:turn.question,answer:parts.join('\n\n')||'回答尚未完成；重新開啟後可再次提問。',at:turn.at??r?.as_of_utc??new Date().toISOString(),...(validAnalysisRef(r?.analysis_ref)?{analysis_ref:r.analysis_ref}:{})};
}
