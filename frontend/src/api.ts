export async function api<T>(path:string, body?:unknown):Promise<T> {
  const response = await fetch(`/api${path}`, {method:body === undefined?'GET':'POST',headers:body===undefined?undefined:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});
  const content = await response.json().catch(()=>({detail:'服務回應格式錯誤，請確認後端已啟動。'}));
  if (!response.ok) throw new Error(typeof content.detail==='string'?content.detail:JSON.stringify(content.detail));
  return content as T;
}
export const key = () => crypto.randomUUID();
