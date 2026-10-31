export type AssistantConfiguration={configured:boolean;enabled:boolean;model:string;provider?:string;provider_label?:string;reason?:string;supports_vision?:boolean;model_options?:string[];effort_options?:string[];default_effort?:string;models?:{id:string;label:string;efforts:string[];default_effort:string}[]};
export const isModelAnalysis=(provider:string)=>['groq_market_analysis','claude_market_analysis','codex_market_analysis'].includes(provider);
export const analysisLabel=(provider:string)=>provider==='codex_market_analysis'?'Codex':provider==='claude_market_analysis'?'Claude Code':provider==='groq_market_analysis'?'Groq':'程式解讀';
export function setupHint(status:AssistantConfiguration|null):string{
 if(!status)return '尚未取得模型設定，請確認本機服務後重新檢查。';
 if(status.provider==='program')return '使用程式盤面與案例摘要，不呼叫外部模型。';
 if(status.provider==='codex'){
  if(status.reason==='cli_upgrade_required')return 'Codex CLI版本缺少必要隔離功能，請先更新官方CLI再重新檢查。';
  if(status.reason==='authentication_required')return 'Codex 尚未登入。請在本機終端執行 codex login，再重新檢查。';
  if(!status.configured)return 'Codex尚未就緒，請確認官方CLI已安裝，並執行 codex login。模型清單依個人帳戶提供。';
 }
 if(status.reason==='authentication_required')return 'Claude Code 尚未登入。請在本機終端執行 claude auth login，再重新檢查。';
 if(status.reason==='cli_not_installed')return '找不到官方 Claude Code，請先安裝並完成登入。';
 if(status.reason==='cli_probe_failed')return '無法確認 Claude Code 狀態，請在終端檢查版本與登入。';
 if(!status.configured)return '模型尚未設定；仍可使用程式盤面與案例摘要。';
 if(!status.enabled)return '模型已設定但未啟用，請使用對應的本機啟動方式。';
 return `${status.provider_label??'語言模型'} 已就緒。送出問題時會使用所選模型解讀去識別摘要。`;
}
