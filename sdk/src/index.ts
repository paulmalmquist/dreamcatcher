export type Reference = `${string}@${number}.${number}.${number}${string}`;
export type QueryResult<T> = { rows:T[]; truncated:boolean; reference?:string; job_id?:string };
export type ClientOptions = {baseUrl:string;appId:string;getToken:()=>string|Promise<string>;fetch?:typeof globalThis.fetch};
export class DreamcatcherError extends Error {
 constructor(public readonly status:number,public readonly details:unknown){super(typeof details==='string'?details:JSON.stringify(details));this.name='DreamcatcherError'}
}
export function createDreamcatcher(options:ClientOptions){
 const base=new URL(options.baseUrl);
 if(base.username||base.password||base.search||base.hash)throw Error('Use an origin URL without credentials, query, or fragment');
 if(base.protocol!=='https:'&&!(base.protocol==='http:'&&['localhost','127.0.0.1','[::1]'].includes(base.hostname)))throw Error('HTTPS is required except for localhost development');
 const fetcher=options.fetch??globalThis.fetch;
 async function request<T>(path:string,body?:unknown):Promise<T>{
  const token=await options.getToken();if(!token)throw Error('A short-lived app-scoped token is required');
  const response=await fetcher(new URL('/api'+path,base),{method:body?'POST':'GET',headers:{Authorization:'Bearer '+token,...(body?{'Content-Type':'application/json'}:{})},body:body?JSON.stringify(body):undefined,redirect:'error'});
  const value=await response.json();if(!response.ok)throw new DreamcatcherError(response.status,value.detail??value);return value as T;
 }
 return {
  identity:()=>request<{id:string;name:string;email:string;groups:string[]}>('/me'),
  queries:{run:<T=Record<string,unknown>>(reference:Reference,parameters:Record<string,unknown>)=>request<QueryResult<T>>('/execute/query',{app_id:options.appId,reference,parameters})},
  skills:{run:<T=Record<string,unknown>>(reference:Reference,input:Record<string,unknown>)=>request<{results:QueryResult<T>[]}>('/execute/skill',{app_id:options.appId,reference,parameters:input})}
 };
}
