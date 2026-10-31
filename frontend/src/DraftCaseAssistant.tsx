import {useState} from 'react';
import {api} from './api';
import AssistantControl,{useAssistantSettings} from './AssistantControl';
import {LiveAssistantReply,type MarketReply} from './LiveAssistant';

export default function DraftCaseAssistant({draftId}:{draftId:string}){
 const assistantSettings=useAssistantSettings();
 const [busy,setBusy]=useState(false),[error,setError]=useState(''),[reply,setReply]=useState<MarketReply|null>(null);
 const explain=async()=>{if(busy)return;setBusy(true);setError('');try{setReply(await api<MarketReply>('/assistant/draft-chat',{draft_id:draftId,message:'解釋這筆草稿的盤面與相似案例：像在哪、差異在哪？若沒有符合案例，請說明原因並整理盤面。',llm_enabled:true,...assistantSettings.requestOptions}));}catch(e){setError(e instanceof Error?e.message:'無法解釋草稿快照');}finally{setBusy(false);}};
 return <section className="draft-case-assistant" aria-label="草稿快照解釋"><h3>這筆草稿的盤面與案例</h3><p className="fine">使用草稿建立時同一份資料，不讀取新行情。解釋不延長草稿期限，也不代你確認委託。</p>
  <AssistantControl settings={assistantSettings} busy={busy}/>
  <button type="button" disabled={busy} onClick={()=>void explain()}>{busy?'整理原快照…':'解釋此草稿的盤面與案例'}</button>
  {error&&<p role="alert" className="modal-error">{error}</p>}{reply&&<LiveAssistantReply reply={reply}/>}
 </section>;
}
