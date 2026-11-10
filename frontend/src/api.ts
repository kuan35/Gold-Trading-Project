export async function readAPIResponse<T>(response:Response):Promise<T>{
  let content:unknown;
  try{content=JSON.parse(await response.text());}
  catch{throw new Error(response.ok?'服務回應格式無效，請稍後再試。':`服務處理失敗（HTTP ${response.status}），請稍後重試；已填欄位會保留。`);}
  if(!response.ok){
    const detail=content&&typeof content==='object'&&'detail' in content?content.detail:null;
    throw new Error(typeof detail==='string'?detail:`服務請求未完成（HTTP ${response.status}），請核對欄位或稍後重試。`);
  }
  if(content===null)throw new Error('服務回應格式無效，請稍後再試。');
  return content as T;
}
export async function api<T>(path:string, body?:unknown):Promise<T> {
  if (import.meta.env.MODE === 'pages') {
    const {browserAPI}=await import('./demo');
    return await browserAPI(path,body) as T;
  }
  const response = await fetch(`/api${path}`, {method:body === undefined?'GET':'POST',headers:body===undefined?undefined:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});
  return await readAPIResponse<T>(response);
}
export const key = () => crypto.randomUUID();
