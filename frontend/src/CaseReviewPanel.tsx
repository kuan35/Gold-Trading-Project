import {useEffect,useRef,useState} from 'react';import {api} from './api';
import AssistantControl,{useAssistantSettings} from './AssistantControl';
import {selectionLabel} from './modelSettings';
import {caseReviewScope,matchingCaseReview,casePreviewUrl} from './caseReviewScope';

type Preview={snapshot_id:string;case_ref?:string|null;image_url:string;rows:string[];columns:string[];basis:string};
type Reply={snapshot_id:string;case_ref?:string|null;message:string;notice?:string;provider?:string;llm_status:string;model?:string;requested_effort?:string;sections?:{title:string;text:string}[]};
type Scoped<T>={scope:string;value:T};
export default function CaseReviewPanel({snapshotId,caseRef}:{snapshotId:string;caseRef?:string}){
 const assistantSettings=useAssistantSettings(),{status}=assistantSettings,scope=caseReviewScope(snapshotId,caseRef);
 const [vision,setVision]=useState(false),[image,setImage]=useState<Scoped<Preview>|null>(null),[reply,setReply]=useState<Scoped<Reply>|null>(null);
 const [busyScope,setBusyScope]=useState<string|null>(null),[error,setError]=useState<Scoped<string>|null>(null);
 const request=useRef(0),activeScope=useRef(scope);activeScope.current=scope;
 const shownImage=image?.scope===scope?image.value:null,shownReply=reply?.scope===scope?reply.value:null,shownError=error?.scope===scope?error.value:'',busy=busyScope===scope;
 useEffect(()=>{if(status?.supports_vision===false)setVision(false);},[status?.supports_vision]);
 useEffect(()=>{request.current++;setImage(null);setReply(null);setVision(false);setError(null);setBusyScope(null);return()=>{request.current++;};},[scope]);
 const run=async(onlyPreview=false)=>{
  const id=++request.current,current=()=>id===request.current&&activeScope.current===scope;
  const options={...assistantSettings.requestOptions};setBusyScope(scope);setError(null);
  try{
   if(onlyPreview){
    const value=await api<Preview>(casePreviewUrl(snapshotId,caseRef));
    if(!matchingCaseReview(value,snapshotId,caseRef)||!value.image_url.startsWith('data:image/png;base64,')||(caseRef&&JSON.stringify(value.rows)!==JSON.stringify(['查詢',caseRef])))throw Error('圖像與目前案例不一致，未顯示。');
    if(current())setImage({scope,value});
   }else{
    const value=await api<Reply>(`/assistant/snapshots/${encodeURIComponent(snapshotId)}/case-review`,{enabled:true,vision,case_ref:caseRef,...options});
    if(!matchingCaseReview(value,snapshotId,caseRef))throw Error('解讀與目前案例不一致，未顯示。');
    if(current())setReply({scope,value});
   }
  }catch(e){if(current())setError({scope,value:e instanceof Error?e.message:'分析讀取失敗'});}
  finally{if(current())setBusyScope(null);}
 };
 return <details className="cw-case-review"><summary>{caseRef?'讓助手分析'+caseRef:'讓助手分析這次檢索出的案例'}</summary>
  <p>{caseRef?'只分析目前選取的'+caseRef+'，依序說明相同點、重要差異與持倉過程。':'依原快照比較進場前差異、原單結果及已知持倉過程。'}程式計算數字，助手負責解釋。</p>
  <AssistantControl settings={assistantSettings} busy={busy}/>
  {status?.supports_vision&&<label><input type="checkbox" aria-label="送出K線圖" checked={vision} disabled={busy} onChange={e=>setVision(e.target.checked)}/>同時送出去識別K線圖</label>}
  <div className="cw-actions"><button disabled={busy} onClick={()=>void run(true)}>預覽K線圖</button><button disabled={busy} onClick={()=>void run()}>{caseRef?'分析目前案例':'分析歷史案例'}</button></div>
  {shownImage&&<><p>由上到下：{shownImage.rows.join('、')}；左欄五分鐘、右欄一小時。</p><img style={{maxWidth:'100%',height:'auto'}} src={shownImage.image_url} alt="目前選取案例與查詢的匿名進場前K線比較圖"/><p className="fine">{shownImage.basis}</p></>}
  {busy&&<p role="status">讀取原案例快照…</p>}{shownError&&<p role="alert">{shownError}</p>}
  {shownReply&&<><small>{shownReply.provider==='program'?'程式摘要':selectionLabel(shownReply.model,shownReply.requested_effort)}</small>
   {shownReply.notice&&<p role="status">{shownReply.notice}</p>}
   {shownReply.sections?.length?<div className="case-review-sections">{shownReply.sections.map((section,index)=><section key={index}><h4>{section.title}</h4><p style={{whiteSpace:'pre-wrap'}}>{section.text}</p></section>)}</div>:<p className="explanation" style={{whiteSpace:'pre-wrap'}}>{shownReply.message}</p>}
  </>}
 </details>;
}
