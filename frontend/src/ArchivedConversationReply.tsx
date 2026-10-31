import type {ArchiveTurn} from './deskConversations';
export default function ArchivedConversationReply({record}:{record:ArchiveTurn}){
 const long=record.answer.length>800;
 return <div className="pd-archived"><small>歷史文字與數值 · {new Date(record.at).toLocaleString('zh-TW')} · 不套用到委託</small>
  {long?<><p>{record.answer.slice(0,220)}…</p><details><summary>展開完整回覆與數據</summary><p>{record.answer}</p></details></>:<p>{record.answer}</p>}
 </div>;
}
