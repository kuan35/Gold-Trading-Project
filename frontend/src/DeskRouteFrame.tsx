import {useEffect,useRef,type ReactNode} from 'react';
import type {DemoMarket} from './demoMarket';
import {DeskIcon} from './DeskChrome';
import {AgentRail,AgentTopbar,railCommand,type ReplayBar} from './experience/AgentDesk';

export type DeskView='assistant'|'replay'|'live';
type Props={historyBrowsing?:boolean;view:DeskView;market:DemoMarket|null;light:boolean;publicMode:boolean;busy:boolean;onNavigate:(view:DeskView)=>void;onSection:(section:'main'|'account'|'cases')=>void;onToggleTheme:()=>void;replay?:ReplayBar|null;children:ReactNode};

export default function DeskRouteFrame({historyBrowsing=false,view,market,light,publicMode,busy,onNavigate,onSection,onToggleTheme,replay,children}:Props){
 const secondary=view!=='assistant',body=useRef<HTMLDivElement>(null),first=useRef(true);
 // Route change keeps children mounted; only the content area fades in, the rail stays put.
 useEffect(()=>{if(first.current){first.current=false;return;}if(window.matchMedia('(prefers-reduced-motion: reduce)').matches)return;body.current?.animate([{opacity:0,transform:'translateY(6px)'},{opacity:1,transform:'none'}],{duration:240,easing:'cubic-bezier(.22,1,.36,1)'});},[view]);
 // Keep both wrappers and the children slot stable across routes: shared drafts stay mounted.
 return <div className={`pd-route-frame pd-view-${view} ${secondary?'pd-route-secondary ag-page':''} ${!publicMode||secondary?'ag-shell':''} ${publicMode?'pd-public':''}`}>
  {(!publicMode||secondary)&&<AgentRail active={view} busy={busy} onNavigate={onNavigate} onNew={view==='assistant'?()=>railCommand('new'):undefined} onHistory={view==='assistant'?()=>railCommand('history'):undefined}/>}
  <div ref={body} className="pd-route-body">
   {secondary&&<>{publicMode?<header className="pd-market pd-public-header"><span className="pd-symbol">Gold Desk <small>公開展示 · 合成回放</small></span><button type="button" aria-label={light?'切換深色':'切換淺色'} onClick={onToggleTheme}><DeskIcon name="sun"/></button></header>:historyBrowsing?<header className="ag-topbar history-topbar"><h1>歷史看盤</h1><span>獨立查看日期 · 不改動模擬帳戶</span><button type="button" onClick={onToggleTheme} aria-label={light?'切換深色':'切換淺色'}><DeskIcon name="sun"/></button></header>:<AgentTopbar market={market} light={light} onTheme={onToggleTheme} title={view==='live'?'即時看盤':'歷史回放'} replay={view==='replay'?replay:null}/>}</>}
   {children}
  </div>
 </div>;
}
