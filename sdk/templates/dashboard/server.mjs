import http from 'node:http';
import {readFile} from 'node:fs/promises';
import {forRequest} from '@dreamcatcher/sdk';
const production=process.env.DC_ENV==='production';
if(production&&process.env.DC_TOKEN)throw Error('Production forbids a shared user token');
if(!process.env.DC_APP_ID||!process.env.DC_GATEWAY_ORIGIN)throw Error('Set DC_APP_ID and DC_GATEWAY_ORIGIN');
const manifest=JSON.parse(await readFile(new URL('./dreamcatcher.json',import.meta.url)));
await readFile(new URL('./dist/index.html',import.meta.url)); // Missing SPA output prevents readiness/startup.
const mime={'/app.js':'text/javascript','/style.css':'text/css'};
http.createServer(async(req,res)=>{
 res.setHeader('Cache-Control','no-store');res.setHeader('X-Content-Type-Options','nosniff');
 res.setHeader('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'");
 const path=new URL(req.url,'http://localhost').pathname;
 if(['/healthz','/readyz'].includes(path)){res.writeHead(200,{'Content-Type':'application/json'});res.end('{"status":"ok"}');return}
 try{
  // WORK-CONNECT: private-edge. The edge strips caller-supplied token headers and
  // injects a per-user, app-scoped token. The gateway validates it, not this header.
  // Direct container ingress must be blocked. Never put this token in HTML/JS.
  const token=req.headers['x-dreamcatcher-runtime-token']??(!production?process.env.DC_TOKEN:undefined);
  if(typeof token!=='string'||!token){res.writeHead(401);res.end('Authenticated runtime session required');return}
  const dc=forRequest({baseUrl:process.env.DC_GATEWAY_ORIGIN,appId:process.env.DC_APP_ID,token});
  await dc.context(); // Recheck sharing, current release and policy on every request.
  if(path==='/api/dashboard'&&req.method==='POST'){
   let body='';for await(const chunk of req){body+=chunk;if(Buffer.byteLength(body)>4096)throw Error('Input too large')}
   const {program_id}=JSON.parse(body);
   const data=await dc.queries.run(manifest.queries[0],{program_id});
   res.writeHead(200,{'Content-Type':'application/json'});res.end(JSON.stringify(data));return;
  }
  if(path.startsWith('/api/')||!['GET','HEAD'].includes(req.method)){res.writeHead(404);res.end();return}
  const file=mime[path]?path:'/index.html';
  res.writeHead(200,{'Content-Type':mime[path]??'text/html'});
  res.end(req.method==='HEAD'?undefined:await readFile(new URL('./dist'+file,import.meta.url)));
 }catch(e){res.writeHead([401,403,409].includes(e.status)?e.status:503,{'Content-Type':'application/json'});res.end(JSON.stringify({error:'Governed data is unavailable. Contact your app owner.'}))}
}).listen(Number(process.env.PORT??8080),production?'0.0.0.0':'127.0.0.1');
