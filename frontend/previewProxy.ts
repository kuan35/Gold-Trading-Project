// Only our explicitly configured loopback UI origins may use the dev proxy for writes.
export const PREVIEW_ORIGINS=['http://127.0.0.1:8766','http://localhost:8766','http://127.0.0.1:5173','http://localhost:5173'];
export function trustedPreviewOrigin(origin:string|undefined):string|undefined{
 return origin&&PREVIEW_ORIGINS.includes(origin)?'http://127.0.0.1:8765':undefined;
}
