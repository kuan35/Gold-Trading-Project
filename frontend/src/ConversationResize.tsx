import {useRef,type RefObject} from 'react';
import {clampChatSize,keyboardChatSize,resizeChat,SIZE_LIMITS,type ChatAxis} from './conversationSizing';
export default function ConversationResize({axis,value,target,onChange}:{axis:ChatAxis;value:number|null;target:RefObject<HTMLDivElement|null>;onChange:(value:number)=>void}){
 const drag=useRef<{id:number;start:number;size:number;width:number}|null>(null),horizontal=axis==='height';
 const measure=()=>{const el=target.current;if(!el)return horizontal?320:70;const r=el.getBoundingClientRect();return horizontal?r.height:100*(el.firstElementChild?.getBoundingClientRect().width??r.width*.7)/Math.max(1,r.width);};
 const cancel=()=>{drag.current=null;};
 return <div className={'cw-resize cw-resize-'+axis} role="separator" tabIndex={0} aria-label={horizontal?'調整聊天高度':'調整聊天寬度'} aria-orientation={horizontal?'horizontal':'vertical'} aria-controls="conversation-log" aria-valuemin={SIZE_LIMITS[axis].min} aria-valuemax={SIZE_LIMITS[axis].max} aria-valuenow={clampChatSize(axis,value??(horizontal?320:70))} aria-valuetext={value===null?'自動大小':`${value}${horizontal?'像素':'%'}`} title={horizontal?'拖曳調整高度；上下鍵亦可調整':'拖曳調整寬度；左右鍵亦可調整'}
  onPointerDown={e=>{if(e.button!==0)return;const el=target.current;if(!el)return;e.preventDefault();e.currentTarget.focus();e.currentTarget.setPointerCapture(e.pointerId);drag.current={id:e.pointerId,start:horizontal?e.clientY:e.clientX,size:value??measure(),width:el.getBoundingClientRect().width};}}
  onPointerMove={e=>{const d=drag.current;if(d&&d.id===e.pointerId)onChange(resizeChat(axis,d.size,(horizontal?e.clientY:e.clientX)-d.start,d.width));}}
  onPointerUp={e=>{if(drag.current?.id!==e.pointerId)return;cancel();if(e.currentTarget.hasPointerCapture(e.pointerId))e.currentTarget.releasePointerCapture(e.pointerId);}}
  onPointerCancel={cancel} onLostPointerCapture={cancel}
  onKeyDown={e=>{const next=keyboardChatSize(axis,value??measure(),e.key);if(next!==null){e.preventDefault();onChange(next);}}}>
  <span aria-hidden="true"/>{horizontal&&<small aria-hidden="true">拖曳調整高度</small>}
 </div>;
}
