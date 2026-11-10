import {useCallback,useEffect,useRef,useState,type ReactNode} from 'react';
import {Command} from 'cmdk';
import {Toaster,toast} from 'sonner';
import {AnimatePresence,motion} from 'motion/react';
import {DeskIcon} from '../DeskChrome';
import ReminderNotifications from '../ReminderNotifications';

export type ExperienceView='assistant'|'replay'|'live';
export type ExperienceCommand={type:'navigate';view:ExperienceView}|{type:'step';bars:number}|{type:'theme'}|{type:'reset'}|{type:'conversation';action:'new'|'history'};

function Palette({open,onOpenChange,run}:{open:boolean;onOpenChange:(v:boolean)=>void;run:(c:ExperienceCommand)=>void}){
 const [search,setSearch]=useState('');
 useEffect(()=>{if(!open)setSearch('');},[open]);
 const go=(c:ExperienceCommand)=>{onOpenChange(false);run(c);};
 return <AnimatePresence>{open&&<motion.div className="gx-palette-backdrop" initial={{opacity:0}} animate={{opacity:1}} exit={{opacity:0,transition:{duration:.12}}} onClick={()=>onOpenChange(false)}>
  <motion.div className="gx-palette" initial={{opacity:0,y:-18,scale:.97}} animate={{opacity:1,y:0,scale:1}} exit={{opacity:0,y:-10,scale:.98,transition:{duration:.12}}} transition={{type:'spring',stiffness:420,damping:32}} onClick={e=>e.stopPropagation()}>
   <Command label="Gold Desk 指令面板" loop onKeyDown={e=>{if(e.key==='Escape'){e.preventDefault();e.stopPropagation();onOpenChange(false);}}}>
    <Command.Input autoFocus value={search} onValueChange={setSearch} placeholder="搜尋頁面、切換主題或回放操作…"/>
    <Command.List>
     <Command.Empty>找不到符合的指令</Command.Empty>
     <Command.Group heading="前往頁面">
      <Command.Item value="交易對話 assistant chat" onSelect={()=>go({type:'navigate',view:'assistant'})}><DeskIcon name="chat"/>交易對話<kbd>G C</kbd></Command.Item>
      <Command.Item value="即時看盤 live chart" onSelect={()=>go({type:'navigate',view:'live'})}><DeskIcon name="chart"/>即時看盤<kbd>G L</kbd></Command.Item>
      <Command.Item value="歷史回放 replay" onSelect={()=>go({type:'navigate',view:'replay'})}><DeskIcon name="replay"/>歷史回放<kbd>G R</kbd></Command.Item>
     </Command.Group>
     <Command.Group heading="聊天管理">
      <Command.Item value="新增對話 new conversation" onSelect={()=>go({type:'conversation',action:'new'})}><DeskIcon name="plus"/>新增對話</Command.Item>
      <Command.Item value="對話紀錄 history conversations" onSelect={()=>go({type:'conversation',action:'history'})}><DeskIcon name="chat"/>對話紀錄</Command.Item>
     </Command.Group>
     <Command.Group heading="回放操作">
      <Command.Item value="下一根 推進 5分 step next" onSelect={()=>go({type:'step',bars:1})}><DeskIcon name="arrow"/>推進一根 K 棒<kbd>→</kbd></Command.Item>
      <Command.Item value="推進 30分 step" onSelect={()=>go({type:'step',bars:6})}><DeskIcon name="arrow"/>推進 30 分鐘</Command.Item>
      <Command.Item value="推進 1小時 step hour" onSelect={()=>go({type:'step',bars:12})}><DeskIcon name="arrow"/>推進 1 小時</Command.Item>
      <Command.Item value="重設回放 reset" onSelect={()=>go({type:'reset'})}><DeskIcon name="replay"/>重設回放</Command.Item>
     </Command.Group>
     <Command.Group heading="介面">
      <Command.Item value="切換深淺色 theme" onSelect={()=>go({type:'theme'})}><DeskIcon name="sun"/>切換深色／淺色<kbd>T</kbd></Command.Item>
     </Command.Group>
    </Command.List>
    <div className="gx-palette-foot"><span><kbd>↑</kbd><kbd>↓</kbd> 選擇</span><span><kbd>Enter</kbd> 執行</span><span><kbd>Esc</kbd> 關閉</span></div>
   </Command>
  </motion.div>
 </motion.div>}</AnimatePresence>;
}

const typing=(t:EventTarget|null)=>t instanceof HTMLElement&&(t.isContentEditable||['INPUT','TEXTAREA','SELECT'].includes(t.tagName));

export default function Experience({view,light,error,notice,run,children,environment='demo'}:{view:ExperienceView;light:boolean;error:string;notice:string;run:(c:ExperienceCommand)=>void;children:ReactNode;environment?:'demo'|'live'}){
 const [open,setOpen]=useState(false),stage=useRef<HTMLDivElement>(null);
 const showReminder=useCallback((conversationId?:string)=>{run({type:'navigate',view:'assistant'});requestAnimationFrame(()=>window.dispatchEvent(new CustomEvent('gd:trading-tools',{detail:{tab:'alerts',conversationId}})));},[run]);
 // Keep the golden ambience static. Pointer-driven root CSS writes force every
 // surface to recalculate styles during scrolling, resizing and chart gestures.
 useEffect(()=>{if(error)toast.error(error);},[error]);
 useEffect(()=>{if(notice)toast.message(notice);},[notice]);
 useEffect(()=>{const open=()=>setOpen(true);window.addEventListener('gd:palette',open);return()=>window.removeEventListener('gd:palette',open);},[]);
 useEffect(()=>{
  let pendingG=false,timer=0;
  const key=(e:KeyboardEvent)=>{
   if((e.metaKey||e.ctrlKey)&&e.key.toLowerCase()==='k'){e.preventDefault();setOpen(v=>!v);return;}
   if(open&&e.key==='Escape'){e.preventDefault();setOpen(false);return;}
   if(open||typing(e.target)||e.metaKey||e.ctrlKey||e.altKey||document.querySelector('dialog[open]'))return;
   const k=e.key.toLowerCase();
   if(pendingG){pendingG=false;const map:Record<string,ExperienceView>={c:'assistant',l:'live',r:'replay'};if(map[k]){e.preventDefault();run({type:'navigate',view:map[k]});}return;}
   if(k==='g'){pendingG=true;window.clearTimeout(timer);timer=window.setTimeout(()=>{pendingG=false;},900);return;}
   if(k==='t'){run({type:'theme'});return;}
   if(e.key==='ArrowRight'&&view==='replay'){e.preventDefault();run({type:'step',bars:1});}
  };
  window.addEventListener('keydown',key);return()=>window.removeEventListener('keydown',key);
 },[open,run,view]);
 return <>
  <div className="gx-ambient" aria-hidden="true"><i/><i/><i/></div>
  <div ref={stage} className="gx-stage">{children}</div>
  <Palette open={open} onOpenChange={setOpen} run={run}/>
  <Toaster theme={light?'light':'dark'} position="top-right" richColors closeButton toastOptions={{className:'gx-toast'}}/>
  <ReminderNotifications onView={showReminder} environment={environment}/>
 </>;
}
