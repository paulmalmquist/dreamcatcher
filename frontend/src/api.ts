export type Identity={id:string;email:string;name:string;role:'admin'|'reviewer'|'builder'|'viewer';groups:string[];csrf:string;demo:boolean};
let csrf='';
export function setCsrf(value:string){csrf=value}
export async function api<T=any>(path:string,method='GET',body?:unknown):Promise<T>{
 const form=body instanceof FormData;
 const response=await fetch('/api'+path,{method,credentials:'same-origin',headers:{...(body&&!form?{'Content-Type':'application/json'}:{}),...(method!=='GET'?{'X-CSRF-Token':csrf}:{})},body:body?(form?body:JSON.stringify(body)):undefined});
 const type=response.headers.get('content-type')||'';
 const data=type.includes('json')?await response.json():await response.text();
 if(!response.ok)throw new Error(typeof data==='string'?data:typeof data.detail==='string'?data.detail:JSON.stringify(data.detail||data));
 if(data?.csrf)setCsrf(data.csrf);
 return data as T;
}
export async function download(path:string,filename:string){const r=await fetch('/api'+path,{credentials:'same-origin'});if(!r.ok)throw Error('Download failed; sign in and confirm access.');const u=URL.createObjectURL(await r.blob());const a=document.createElement('a');a.href=u;a.download=filename;a.click();setTimeout(()=>URL.revokeObjectURL(u),1000)}
