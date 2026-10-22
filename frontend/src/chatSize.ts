export const CHAT_HEIGHT_KEY='gold-desk-chat-height-v1';
export function savedChatHeight(raw:string|null):number|null{
 if(raw===null||!/^\d+$/.test(raw))return null;
 const value=Number(raw);return Number.isSafeInteger(value)&&value>=210&&value<=1000?value:null;
}
