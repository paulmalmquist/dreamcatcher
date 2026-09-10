import test from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import {once} from 'node:events';
import {createHandler} from '../integrations/private-edge/server.mjs';
import {createMemorySessionStore} from '../integrations/private-edge/session-store.mjs';

async function fixture(t,sessionStore){
 const app='a'.repeat(24),host=app+'.apps.example.invalid:9443',origin='https://'+host;
 let time=1000,contextStatus=200,submission='release-one';
 const calls=[];
 const handler=createHandler({controlOrigin:'https://gateway.example.invalid',galleryOrigin:'https://gallery.example.invalid',edgeKey:'test-only-edge-key-'+ 'e'.repeat(32),now:()=>time,sessionStore,
  getRoutes:async()=>({[host]:{appId:app,submissionId:'release-one',origin,upstream:'http://private-container:8080'}}),
  fetcher:async(url,options)=>{
   calls.push({url:new URL(url),options});
   if(url.pathname==='/api/v2/edge/exchange'){const code=JSON.parse(options.body).code;return Response.json({token:code.startsWith('other')?'different-user-token':'server-side-runtime-token',expires_at:60,submission_id:'release-one'})}
   if(url.pathname.endsWith('/context'))return Response.json({submission_id:submission},{status:contextStatus});
   return new Response('<h1>Private dashboard</h1>',{headers:{'Content-Type':'text/html','Set-Cookie':'__Host-dc_app=stolen','Access-Control-Allow-Origin':'*','Content-Security-Policy':"default-src *"}});
  }});
 const server=http.createServer(handler).listen(0,'127.0.0.1');await once(server,'listening');
 t.after(()=>new Promise(resolve=>server.close(resolve)));
 const base='http://127.0.0.1:'+server.address().port;
 // node:http preserves a deliberate Host header; Fetch may normalize it.
 const request=(path='/',options={})=>new Promise((resolve,reject)=>{
  const req=http.request(base+path,{method:options.method??'GET',headers:{Host:host,...options.headers}},res=>{
   const chunks=[];res.on('data',chunk=>chunks.push(chunk));res.on('end',()=>resolve(new Response(Buffer.concat(chunks),{status:res.statusCode,headers:res.headers})));
  });req.on('error',reject);req.end(options.body);
 });
 async function launch(code='z'.repeat(50)){
  const r=await request('/_dc/launch',{method:'POST',headers:{Origin:'https://gallery.example.invalid','Content-Type':'application/x-www-form-urlencoded'},body:'code='+code});
  assert.equal(r.status,303);assert.equal(r.headers.get('location'),'/');
  const cookie=r.headers.get('set-cookie');assert.match(cookie,/HttpOnly; Secure; SameSite=Lax/);
  assert(!cookie.includes('server-side-runtime-token'));assert.equal(await r.text(),'');
  return cookie.split(';')[0];
 }
 return {request,launch,calls,host,origin,setContext:(status,sub='release-one')=>{contextStatus=status;submission=sub},expire:()=>{time=61000}};
}

test('edge isolates credentials, revalidates requests and constrains app response headers',async t=>{
 const f=await fixture(t),cookie=await f.launch();
 const r=await f.request('/',{headers:{Cookie:cookie+'; dc_session=gallery-cookie',Authorization:'Bearer attacker','x-dreamcatcher-runtime-token':'attacker'}});
 assert.equal(r.status,200);assert.match(await r.text(),/Private dashboard/);
 assert.equal(r.headers.get('set-cookie'),null);assert.equal(r.headers.get('access-control-allow-origin'),null);
 assert.match(r.headers.get('content-security-policy'),/connect-src 'self'/);
 assert.equal(r.headers.get('cache-control'),'no-store');
 const forwarded=f.calls.at(-1).options.headers;
 assert.equal(forwarded['x-dreamcatcher-runtime-token'],'server-side-runtime-token');
 assert.equal(forwarded.Cookie,undefined);assert.equal(forwarded.Authorization,undefined);
 assert.equal(f.calls.at(-2).url.pathname.endsWith('/context'),true);
 f.setContext(401);
 assert.equal((await f.request('/app.js',{headers:{Cookie:cookie}})).status,401);
 assert.equal(f.calls.at(-1).url.hostname,'gateway.example.invalid');
});

test('two replicas sharing a session adapter preserve separate concurrent user tokens',async t=>{
 const store=createMemorySessionStore({now:()=>1000});
 const a=await fixture(t,store),b=await fixture(t,store);
 const first=await a.launch(),second=await a.launch('other-user-code');
 const results=await Promise.all([b.request('/',{headers:{Cookie:first}}),b.request('/',{headers:{Cookie:second}})]);
 assert(results.every(r=>r.status===200));
 const tokens=b.calls.filter(c=>c.url.hostname==='private-container').map(c=>c.options.headers['x-dreamcatcher-runtime-token']);
 assert.deepEqual(new Set(tokens),new Set(['server-side-runtime-token','different-user-token']));
});
test('production rejects the local in-memory session store',()=>{
 assert.throws(()=>createHandler({controlOrigin:'https://gateway.example.invalid',galleryOrigin:'https://gallery.example.invalid',edgeKey:'x'.repeat(40),getRoutes:async()=>({}),production:true}),/persistent/);
});
test('session adapter capacity and expiry fail closed',async()=>{
 let now=0;const store=createMemorySessionStore({capacity:1,now:()=>now});
 assert.equal(await store.put('one',{expires_at:1,token:'one'}),true);
 assert.equal(await store.put('two',{expires_at:2,token:'two'}),false);
 now=1001;assert.equal(await store.get('one'),undefined);
 assert.equal(await store.put('two',{expires_at:2,token:'two'}),true);
});

test('edge denies cross-origin writes, spoofed headers, unknown hosts and ambiguous cookies',async t=>{
 const f=await fixture(t),cookie=await f.launch();
 assert.equal((await f.request('/',{headers:{'x-dreamcatcher-runtime-token':'forged'}})).status,401);
 assert.equal((await f.request('/',{headers:{Host:'different.apps.example.invalid'}})).status,421);
 assert.equal((await f.request('/',{headers:{Cookie:cookie+'; '+cookie}})).status,401);
 assert.equal((await f.request('/api/dashboard',{method:'POST',headers:{Cookie:cookie,Origin:'https://evil.example'}})).status,403);
 assert.equal((await f.request('/_dc/launch',{method:'POST',headers:{Origin:'https://evil.example','Content-Type':'application/x-www-form-urlencoded'},body:'code=x'})).status,403);
 assert.equal((await f.request('/api/dashboard',{method:'POST',headers:{Cookie:cookie,Origin:f.origin},body:'{}'})).status,200);
});

test('edge denies changed releases, gateway outage and expired local sessions',async t=>{
 const f=await fixture(t),cookie=await f.launch();
 f.setContext(200,'new-release');
 assert.equal((await f.request('/',{headers:{Cookie:cookie}})).status,409);
 f.setContext(500);
 assert.equal((await f.request('/',{headers:{Cookie:cookie}})).status,503);
 f.expire();
 assert.equal((await f.request('/',{headers:{Cookie:cookie}})).status,401);
});
