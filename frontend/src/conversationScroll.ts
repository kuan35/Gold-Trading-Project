// Keep transcript navigation inside its own scrollport; never scroll the page.
export const turnScrollTarget=(scrollTop:number,viewportTop:number,turnTop:number)=>Math.max(0,scrollTop+turnTop-viewportTop-16);
export const nearChatBottom=(scrollHeight:number,clientHeight:number,scrollTop:number)=>scrollHeight-clientHeight-scrollTop<=80;
