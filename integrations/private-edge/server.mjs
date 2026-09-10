/** Reference app edge. Run separately from uploaded containers. No external deps.
 * WORK-CONNECT: private-edge — replace in-memory sessions/routing with your
 * approved edge infrastructure; retain these handoff and revocation semantics.
 */
import https from 'node:https';
import {readFile} from 'node:fs/promises';
import {randomBytes} from 'node:crypto';
import {pathToFileURL} from 'node:url';
import {createMemorySessionStore} from './session-store.mjs';

const policy="default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'";
async function bounded(stream,limit){
 const chunks=[];let size=0;
 for await(const chunk of stream){size+=chunk.length;if(size>limit)throw Error('Size limit');chunks.push(Buffer.from(chunk))}
 return Buffer.concat(chunks);
}
export function createHandler({controlOrigin,galleryOrigin,edgeKey,getRoutes,fetcher=fetch,now=Date.now,sessionStore,production=false}){
 const control=new URL(controlOrigin);
 if(control.protocol!=='https:'&&!(control.protocol==='http:'&&['localhost','127.0.0.1'].includes(control.hostname)))throw Error('Use HTTPS to the control plane');
 if(edgeKey.length<32)throw Error('Set DC_WORKER_EDGE_KEY on the edge only');
 const sessions=sessionStore??createMemorySessionStore({now});
 if(production&&sessions.persistent!==true)throw Error('Production requires an approved persistent edge session adapter');
 async function gateway(path,token,body){
  const r=await fetcher(new URL(path,control),{method:body?'POST':'GET',headers:{Authorization:'Bearer '+token,...(body?{'Content-Type':'application/json'}:{})},body:body?JSON.stringify(body):undefined,redirect:'error',signal:AbortSignal.timeout(10000)});
  if(!r.ok){const e=Error('Access denied');e.status=[401,403,409,429].includes(r.status)?r.status:503;throw e}
  return r.json();
 }
 return async(req,res)=>{
  res.setHeader('Cache-Control','no-store');res.setHeader('Referrer-Policy','no-referrer');
  res.setHeader('X-Content-Type-Options','nosniff');res.setHeader('X-Frame-Options','DENY');
  res.setHeader('Content-Security-Policy',policy);
  // No request/body/cookie logging. Upload workers never control this routing file.
  try{
   const route=(await getRoutes())[req.headers.host];
   if(!route||route.origin!=='https://'+req.headers.host||!/^[a-f0-9]{24}$/.test(route.appId)){res.writeHead(421);res.end('Unknown app origin');return}
   const url=new URL(req.url,route.origin);
   if(url.origin!==route.origin)throw Error('Invalid request target');
   if(url.pathname==='/_dc/launch'){
    if(req.method!=='POST'||req.headers.origin!==galleryOrigin||!req.headers['content-type']?.startsWith('application/x-www-form-urlencoded')){res.writeHead(403);res.end('Launch from Dreamcatcher');return}
    const form=new URLSearchParams((await bounded(req,4096)).toString());
    if(form.getAll('code').length!==1)throw Error('One code required');
    const result=await gateway('/api/v2/edge/exchange',edgeKey,{code:form.get('code'),app_id:route.appId,origin:route.origin});
    const id=randomBytes(32).toString('base64url');
    if(!await sessions.put(id,{...result,appId:route.appId,origin:route.origin})){res.writeHead(503);res.end('Try again shortly');return}
    const ttl=Math.max(0,Math.floor(result.expires_at-now()/1000));
    res.setHeader('Set-Cookie',`__Host-dc_app=${id}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=${ttl}`);
    res.writeHead(303,{Location:'/'});res.end();return;
   }
   if(url.pathname.startsWith('/_dc/')){res.writeHead(404);res.end();return}
   const cookies=(req.headers.cookie??'').split(';').map(s=>s.trim()).filter(s=>s.startsWith('__Host-dc_app='));
   const session=cookies.length===1?await sessions.get(cookies[0].slice('__Host-dc_app='.length)):undefined;
   if(!session||session.expires_at*1000<=now()||session.appId!==route.appId||session.origin!==route.origin){res.writeHead(401);res.end('Session ended. Launch again from Dreamcatcher.');return}
   if(!['GET','HEAD'].includes(req.method)&&req.headers.origin!==route.origin){res.writeHead(403);res.end('Origin is not allowed');return}
   if(!['GET','HEAD','POST','PUT','DELETE'].includes(req.method)){res.writeHead(405);res.end();return}
   // Check outside the uploaded app, including requests for its JS/CSS/HTML.
   const context=await gateway(`/api/v2/runtime/${route.appId}/context`,session.token);
   if(context.submission_id!==route.submissionId||context.submission_id!==session.submission_id){res.writeHead(409);res.end('Release changed. Launch again from Dreamcatcher.');return}
   const upstream=new URL(route.upstream);
   if(!['https:','http:'].includes(upstream.protocol)||upstream.username||upstream.password||upstream.pathname!=='/'||upstream.search||upstream.hash)throw Error('Invalid operator route');
   const body=['GET','HEAD'].includes(req.method)?undefined:await bounded(req,65536);
   // Header allowlist: never forward caller cookies, Authorization, Host, or
   // x-dreamcatcher-runtime-token. Always replace identity with this edge session.
   const r=await fetcher(new URL(url.pathname+url.search,upstream),{method:req.method,
    headers:{'x-dreamcatcher-runtime-token':session.token,'Content-Type':req.headers['content-type']??'application/json',Accept:req.headers.accept??'*/*'},
    body,redirect:'error',signal:AbortSignal.timeout(40000)});
   const payload=r.body?await bounded(r.body,2*1024*1024):Buffer.alloc(0);
   // Do not forward Set-Cookie, Location, CORS or CSP from untrusted app code.
   res.writeHead(r.status,{'Content-Type':r.headers.get('content-type')??'text/plain'});
   res.end(req.method==='HEAD'?undefined:payload);
  }catch(e){res.writeHead(e.status??503,{'Content-Type':'text/plain'});res.end('Access unavailable. Launch again from Dreamcatcher or contact the app owner.')}
 };
}

if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href){
 const env=process.env;
 const production=env.DC_ENV==='production';
 // Operator-installed module only. No user-selected imports or credential lookup.
 const sessionStore=production?(await import(new URL('../../work-edge-sessions.mjs',import.meta.url))).createSessionStore():undefined;
 const handler=createHandler({controlOrigin:env.DC_CONTROL_ORIGIN,galleryOrigin:env.DC_GALLERY_ORIGIN,
  edgeKey:env.DC_WORKER_EDGE_KEY??'',getRoutes:async()=>JSON.parse(await readFile(env.DC_EDGE_ROUTES,'utf8')),sessionStore:await sessionStore,production});
 const server=https.createServer({key:await readFile(env.DC_EDGE_TLS_KEY),cert:await readFile(env.DC_EDGE_TLS_CERT)},handler);
 server.requestTimeout=45000;server.headersTimeout=10000;
 server.listen(Number(env.DC_EDGE_PORT??8443),env.DC_EDGE_BIND??'127.0.0.1');
}
