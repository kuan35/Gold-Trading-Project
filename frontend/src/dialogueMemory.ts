type Turn={question:string;record?:{answer:string};note?:string;reply?:{sections:{text:string}[]}};
export function buildDialogueMemory(turns:Turn[],threadId:string){
 return turns.filter(t=>t.record||t.reply||t.note).slice(-6).map(t=>({thread_id:threadId,question:t.question.slice(0,1500),
  answer:(t.record?.answer??t.reply?.sections.map(s=>s.text).join('\n')??t.note??'').slice(0,1800)}));
}
