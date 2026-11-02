import type {ArchiveTurn} from './deskConversations';
import {useEffect,useState} from 'react';import {loadAnalysis} from './analysisHistory';import type {MarketReply} from './LiveAssistant';import type {ComparisonSelection} from './caseComparisonData';import ConversationReply from './ConversationReply';
type OpenChart=(reply:MarketReply,mode:'analysis'|'cases',period?:'5m'|'15m'|'1h',selection?:ComparisonSelection)=>void;
export function RestoredConversationReply({reply,question,light=false,onChart}:{reply:MarketReply;question:string;light?:boolean;onChart?:OpenChart}){
 return <div className="pd-archived"><small>原分析 · {new Date(reply.as_of_utc).toLocaleString('zh-TW')} · 唯讀回看</small><ConversationReply reply={reply} question={question} light={light} onChart={(mode,period,selection)=>onChart?.(reply,mode,period,selection)}/></div>;
}
export default function ArchivedConversationReply({record,light=false,onChart}:{record:ArchiveTurn;light?:boolean;onChart?:OpenChart}){
 const [reply,setReply]=useState<MarketReply|null>(null),[error,setError]=useState('');
 useEffect(()=>{setReply(null);setError('');if(!record.analysis_ref)return;const controller=new AbortController();void loadAnalysis(record.analysis_ref,{signal:controller.signal}).then(setReply).catch(e=>{if(!controller.signal.aborted)setError(e instanceof Error?e.message:'原分析無法讀取。');});return()=>controller.abort();},[record.analysis_ref]);
 if(reply)return <RestoredConversationReply reply={reply} question={record.question} light={light} onChart={onChart}/>;
 const long=record.answer.length>800;
 return <div className="pd-archived"><small>歷史文字與數值 · {new Date(record.at).toLocaleString('zh-TW')} · 不套用到委託</small>
  {record.analysis_ref&&!error&&<p role="status">正在還原原分析與案例…</p>}{error&&<p role="status">{error}</p>}
  {long?<><p>{record.answer.slice(0,220)}…</p><details><summary>展開完整回覆與數據</summary><p>{record.answer}</p></details></>:<p>{record.answer}</p>}
 </div>;
}
