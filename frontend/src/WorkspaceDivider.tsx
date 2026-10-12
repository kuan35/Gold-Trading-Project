import {useRef,type PointerEvent,type KeyboardEvent} from 'react';
import {DEFAULT_WIDTH,MIN_WIDTH,MAX_WIDTH,resizeWidth} from './terminalLayout';

export default function WorkspaceDivider({width,onChange}:{width:number;onChange:(value:number)=>void}) {
  const drag=useRef<{id:number;x:number;width:number}|null>(null);
  const end=(event:PointerEvent<HTMLDivElement>)=>{
    if(drag.current?.id!==event.pointerId)return;
    drag.current=null;
    if(event.currentTarget.hasPointerCapture(event.pointerId))event.currentTarget.releasePointerCapture(event.pointerId);
  };
  const keyboard=(event:KeyboardEvent<HTMLDivElement>)=>{
    const step=event.shiftKey?32:8;
    const next=event.key==='ArrowLeft'?width+step:event.key==='ArrowRight'?width-step:event.key==='Home'?MIN_WIDTH:event.key==='End'?MAX_WIDTH:null;
    if(next===null)return;
    event.preventDefault();onChange(resizeWidth(next,0));
  };
  return <div className="workspace-divider" role="separator" tabIndex={0} aria-label="調整委託區寬度" aria-orientation="vertical" aria-controls="order-panel" aria-valuemin={MIN_WIDTH} aria-valuemax={MAX_WIDTH} aria-valuenow={width} aria-valuetext={`委託區 ${width} 像素`} title="拖拉調整委託區；方向鍵微調，雙擊還原"
    onKeyDown={keyboard} onDoubleClick={()=>onChange(DEFAULT_WIDTH)}
    onPointerDown={event=>{if(event.button!==0)return;event.preventDefault();event.currentTarget.focus();drag.current={id:event.pointerId,x:event.clientX,width};event.currentTarget.setPointerCapture(event.pointerId);}}
    onPointerMove={event=>{const start=drag.current;if(start?.id===event.pointerId)onChange(resizeWidth(start.width,event.clientX-start.x));}}
    onPointerUp={end} onPointerCancel={end} onLostPointerCapture={()=>{drag.current=null;}}><span aria-hidden="true"/></div>;
}
