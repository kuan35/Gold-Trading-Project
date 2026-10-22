export type ChatAxis='height'|'width';
export const SIZE_LIMITS={height:{min:210,max:1000,step:24},width:{min:44,max:80,step:3}};
export function clampChatSize(axis:ChatAxis,value:number){const {min,max}=SIZE_LIMITS[axis];return Math.round(Math.max(min,Math.min(max,Number.isFinite(value)?value:min)));}
export function resizeChat(axis:ChatAxis,start:number,delta:number,containerWidth=1){return clampChatSize(axis,start+(axis==='width'?delta/Math.max(1,containerWidth)*100:delta));}
export function keyboardChatSize(axis:ChatAxis,value:number,key:string){const {min,max,step}=SIZE_LIMITS[axis];if(key==='Home')return min;if(key==='End')return max;const pair=axis==='height'?['ArrowUp','ArrowDown']:['ArrowLeft','ArrowRight'];return key===pair[0]?clampChatSize(axis,value-step):key===pair[1]?clampChatSize(axis,value+step):null;}
