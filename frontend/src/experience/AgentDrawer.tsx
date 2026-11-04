import {useEffect,useState,type ReactNode} from 'react';
import {MiniChart} from './AgentDesk';import type {DemoMarket} from '../demoMarket';
import DeskAccountTray from '../DeskAccountTray';import BrokerAccountPanel from '../BrokerAccountPanel';
import type {DraftChartState} from '../DraftChartOverlay';
export type DrawerTab='order'|'chart'|'account'|'records';
export default function AgentDrawer({open,tab,onTab,onClose,light,market,order,resizer,draft,tools}:{open:boolean;tab:DrawerTab;onTab:(tab:DrawerTab)=>void;onClose:()=>void;light:boolean;market:DemoMarket|null;order:ReactNode;resizer?:ReactNode;draft?:DraftChartState;tools?:ReactNode}){
 const [expanded,setExpanded]=useState(false);
 const [seen,setSeen]=useState({account:tab==='account',records:tab==='records'});
 useEffect(()=>{if(open&&(tab==='account'||tab==='records'))setSeen(previous=>previous[tab]?previous:{...previous,[tab]:true});},[open,tab]);
 const contentId='ag-context-content';
 return <aside className={`ag-drawer ${expanded?'ag-drawer-expanded':''}`} aria-label="下單與帳戶工作區" hidden={!open} onKeyDown={e=>{if(e.key==='Escape'){if(expanded)setExpanded(false);else onClose();e.stopPropagation();}}}>
  {resizer}<header><div className="ag-seg ag-tabs" role="tablist" aria-label="右側工作區">{([['order','下單'],['chart','即時圖'],['account','帳戶'],['records','紀錄']] as const).map(([id,label])=><button key={id} id={'ag-tab-'+id} role="tab" type="button" aria-selected={id===tab} aria-controls={id==='order'?'ag-order-panel':contentId} onClick={()=>onTab(id)}>{label}</button>)}</div><button type="button" className="ag-icon-btn" aria-label="收合側欄" onClick={()=>{setExpanded(false);onClose();}}>×</button></header>
  <div className="ag-drawer-body">
   <div className="ag-order-slot" id="ag-order-panel" role="tabpanel" aria-labelledby="ag-tab-order" hidden={tab!=='order'}>{order}</div>
   {tab!=='order'&&<div id={contentId} role="tabpanel" aria-labelledby={'ag-tab-'+tab}>
    <button type="button" className="ag-ghost ag-account-full" onClick={()=>setExpanded(v=>!v)}>{expanded?'還原側欄大小':'放大檢視'}</button>
    {open&&tab==='chart'&&<MiniChart light={light} draft={draft}/>}
   </div>}
   {(seen.account||tab==='account')&&<div key="retained-account" hidden={!open||tab!=='account'}><DeskAccountTray market={market} idPrefix="drawer-account-"/></div>}
   {(seen.records||tab==='records')&&<div key="retained-records" hidden={!open||tab!=='records'}>{tools??<BrokerAccountPanel market={market} initialTab="history" idPrefix="drawer-records-"/>}</div>}
  </div>
 </aside>;
}
