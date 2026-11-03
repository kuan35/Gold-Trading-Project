import AssistantControl,{type AssistantSettings as Settings} from '../AssistantControl';
export default function AssistantSettings({settings,busy,open,onOpen}:{settings:Settings;busy:boolean;open:boolean;onOpen:(open:boolean)=>void}){
 const provider=settings.selection.provider??settings.status?.provider??'claude_code';
 const name=({claude_code:'Claude Code',codex:'Codex',program:'程式解讀',openai_compatible:'API／Groq'} as Record<string,string>)[provider]??provider;
 return <details className="ag-model-settings" open={open} onToggle={e=>onOpen(e.currentTarget.open)} onKeyDown={e=>{if(e.key==='Escape'){onOpen(false);e.stopPropagation();}}}><summary aria-label="助手設定">{name} <span aria-hidden="true">⌄</span></summary><div className="ag-settings-popover"><AssistantControl settings={settings} busy={busy}/></div></details>;
}
