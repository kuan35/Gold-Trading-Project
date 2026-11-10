import type {MarketReply} from './LiveAssistant';
import type {ModelSelection} from './modelSettings';
type OriginalDraft={id:string;analysis_snapshot_id:string;analysis_as_of_utc:string};
type Result={status:'done';reply:MarketReply}|{status:'error';message:string};
type Post=(path:string,body:unknown,signal:AbortSignal)=>Promise<MarketReply>;
export class DraftAgentSession{
 private generation=0;private controller:AbortController|null=null;
 cancel(){this.generation++;this.controller?.abort();this.controller=null;}
 async start(draft:OriginalDraft,options:Partial<ModelSelection>,post:Post,receive:(value:Result)=>void){
  this.cancel();const generation=this.generation,controller=new AbortController();this.controller=controller;
  const timer=setTimeout(()=>controller.abort(),180000);
  try{
   const reply=await post('/assistant/draft-chat',{draft_id:draft.id,message:'請評估這筆已填的方向、單型、手數、進場價與停損停利。首段標題「這筆委託評估」，簡短說明主要優點或問題、已算出的風險、建議保留或調整的欄位；不要只重複一般多空盤面分析。有相似案例就結合整體歷史結果與這筆草稿的差異，沒有則依盤面與已算風險回答。只依這份固定草稿快照及提供的數值，不代替程式判定委託是否合法，不修改草稿、不確認或送單。',llm_enabled:true,...options},controller.signal);
   if(generation!==this.generation)return;
   if(reply.snapshot_id!==draft.analysis_snapshot_id||reply.as_of_utc!==draft.analysis_as_of_utc||reply.analysis_mode!=='draft_snapshot'||reply.market_status!=='FROZEN')throw Error('助手回覆與原委託快照不一致。');
   receive({status:'done',reply});
  }catch(e){if(generation===this.generation)receive({status:'error',message:controller.signal.aborted?'助手解讀逾時。':e instanceof Error?e.message:'助手解讀失敗。'});}
  finally{clearTimeout(timer);if(generation===this.generation)this.controller=null;}
 }
}
