export type Reference = `${string}@${number}.${number}.${number}${string}`;
export type QueryResult<T> = { rows:T[]; truncated:boolean; reference?:string; job_id?:string; bytes_processed?:number };
export type RuntimeContext = {user:{id:string;name:string;groups:string[]};app_id:string;submission_id:string;version:string;queries:Reference[];skills:Reference[];collections:{name:string;scope:'user';max_bytes:number}[]};
export type StateRecord<T> = {value:T|null;version:number};
export type ClientOptions = {baseUrl:string;appId:string;getToken:()=>string|Promise<string>;fetch?:typeof globalThis.fetch;timeoutMs?:number};
export class DreamcatcherError extends Error {
 constructor(public readonly status:number,public readonly details:unknown){super(typeof details==='string'?details:JSON.stringify(details));this.name='DreamcatcherError'}
}
export function createDreamcatcher(options:ClientOptions){
 const base=new URL(options.baseUrl);
 if(!/^[a-zA-Z0-9-]{1,80}$/.test(options.appId))throw Error('Invalid appId');
 if(base.username||base.password||base.search||base.hash)throw Error('Use an origin URL without credentials, query, or fragment');
 if(base.protocol!=='https:'&&!(base.protocol==='http:'&&['localhost','127.0.0.1','[::1]'].includes(base.hostname)))throw Error('HTTPS is required except for localhost development');
 const fetcher=options.fetch??globalThis.fetch;
 async function request<T>(path:string,body?:unknown,method=body?'POST':'GET'):Promise<T>{
  const token=await options.getToken();if(!token)throw Error('A short-lived app-scoped token is required');
  const response=await fetcher(new URL('/api'+path,base),{method,headers:{Authorization:'Bearer '+token,...(body?{'Content-Type':'application/json'}:{})},body:body?JSON.stringify(body):undefined,redirect:'error',signal:AbortSignal.timeout(options.timeoutMs??35000)});
  let value;try{value=await response.json()}catch{throw new DreamcatcherError(response.status,'Gateway returned a non-JSON response')}
  if(!response.ok)throw new DreamcatcherError(response.status,value.detail??value);return value as T;
 }
 const runtime='/v2/runtime/'+options.appId;
 function segment(value:string){if(!/^[a-zA-Z0-9_-]{1,120}$/.test(value))throw Error('Invalid state key or collection');return encodeURIComponent(value)}
 return {
  identity:()=>request<{id:string;name:string;email:string;groups:string[]}>('/me'),
  queries:{run:<T=Record<string,unknown>>(reference:Reference,parameters:Record<string,unknown>)=>request<QueryResult<T>>('/execute/query',{app_id:options.appId,reference,parameters})},
  skills:{run:<T=Record<string,unknown>>(reference:Reference,input:Record<string,unknown>)=>request<{results:QueryResult<T>[]}>('/execute/skill',{app_id:options.appId,reference,parameters:input})},
  context:()=>request<RuntimeContext>(runtime+'/context'),
  state:{
   get:<T=Record<string,unknown>>(collection:string,key:string)=>request<StateRecord<T>>(runtime+'/state/'+segment(collection)+'/'+segment(key)),
   put:<T extends Record<string,unknown>>(collection:string,key:string,value:T,options:{expectedVersion:number;idempotencyKey:string})=>request<{version:number}>(runtime+'/state/'+segment(collection)+'/'+segment(key),{value,expected_version:options.expectedVersion,idempotency_key:options.idempotencyKey},'PUT')
  },
  events:{emit:(name:'app.open'|'app.error',code:'NONE'|'QUERY_FAILED'|'UNHANDLED'='NONE')=>request<{ok:boolean}>(runtime+'/events',{event:name,code})}
 };
}

/** Construct per authenticated request. Never share a user's token across requests. */
export function forRequest(options:Omit<ClientOptions,'getToken'>&{token:string}){
 const {token,...rest}=options;return createDreamcatcher({...rest,getToken:()=>token});
}
