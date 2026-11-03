import type {MarketReply} from './LiveAssistant';
import type {ModelSelection} from './modelSettings';
import type {ArchivedChart} from './analysisHistory';
export function rebindDraftChart(chart:ArchivedChart|null,before:Pick<MarketReply,'snapshot_id'|'analysis_ref'>,after:Pick<MarketReply,'snapshot_id'|'analysis_ref'>):ArchivedChart|null{
 return chart&&after.analysis_ref&&chart.id===before.snapshot_id&&before.snapshot_id===after.snapshot_id&&chart.analysis_ref===before.analysis_ref?{...chart,analysis_ref:after.analysis_ref}:chart;
}
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
   const reply=await post('/assistant/draft-chat',{draft_id:draft.id,message:'請用白話解釋這份待確認委託的盤面支持、相反依據、相似案例與差異，以及程式算出的停損停利風險。沒有案例時請明說。這是草稿建立時的固定快照，不是現在行情；不要修改草稿或指示送單。',llm_enabled:true,...options},controller.signal);
   if(generation!==this.generation)return;
   if(reply.snapshot_id!==draft.analysis_snapshot_id||reply.as_of_utc!==draft.analysis_as_of_utc||reply.analysis_mode!=='draft_snapshot'||reply.market_status!=='FROZEN')throw Error('助手回覆與原委託快照不一致。');
   receive({status:'done',reply});
  }catch(e){if(generation===this.generation)receive({status:'error',message:controller.signal.aborted?'助手解讀逾時。':e instanceof Error?e.message:'助手解讀失敗。'});}
  finally{clearTimeout(timer);if(generation===this.generation)this.controller=null;}
 }
}
