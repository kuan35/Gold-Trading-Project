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
   const reply=await post('/assistant/draft-chat',{draft_id:draft.id,message:'先用一句白話說明這筆委託的方向、進場條件與主要風險，再解釋支持和相反訊號、相似案例及差異，以及已計算的停損停利風險。歷史配對不足時，請說明不足的是可同時試算多空的歷史情境，不要把它當成盤面沒有方向。只依這份固定草稿快照回答，不要修改草稿或指示送單。',llm_enabled:true,...options},controller.signal);
   if(generation!==this.generation)return;
   if(reply.snapshot_id!==draft.analysis_snapshot_id||reply.as_of_utc!==draft.analysis_as_of_utc||reply.analysis_mode!=='draft_snapshot'||reply.market_status!=='FROZEN')throw Error('助手回覆與原委託快照不一致。');
   receive({status:'done',reply});
  }catch(e){if(generation===this.generation)receive({status:'error',message:controller.signal.aborted?'助手解讀逾時。':e instanceof Error?e.message:'助手解讀失敗。'});}
  finally{clearTimeout(timer);if(generation===this.generation)this.controller=null;}
 }
}
