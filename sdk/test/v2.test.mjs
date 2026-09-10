import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {createDreamcatcher,forRequest} from '../dist/index.js';
import {collect,validate,zip,checkSchema} from '../cli/source.mjs';

test('state CAS request contains no caller-selectable identity',async()=>{
 let sent;const dc=forRequest({baseUrl:'http://localhost:8000',appId:'app-01',token:'request-only',fetch:async(u,o)=>{sent={url:String(u),...o};return new Response('{"version":1}')}});
 await dc.state.put('preferences','dashboard',{program:'program-a'},{expectedVersion:0,idempotencyKey:'request-one'});
 assert.equal(sent.method,'PUT');assert.equal(sent.url,'http://localhost:8000/api/v2/runtime/app-01/state/preferences/dashboard');
 assert.deepEqual(JSON.parse(sent.body),{value:{program:'program-a'},expected_version:0,idempotency_key:'request-one'});
 assert.equal(sent.headers.Authorization,'Bearer request-only');assert.equal(sent.redirect,'error');assert.ok(sent.signal);
});
test('contexts are constructed per request',async()=>{
 const seen=[];const fetch=async(u,o)=>{seen.push(o.headers.Authorization);return new Response('{}')};
 await forRequest({baseUrl:'https://gateway.example.invalid',appId:'app-01',token:'alice',fetch}).context();
 await forRequest({baseUrl:'https://gateway.example.invalid',appId:'app-01',token:'bob',fetch}).context();
 assert.deepEqual(seen,['Bearer alice','Bearer bob']);
});
test('concurrent callers cannot reuse another callers token or result',async()=>{
 const fetch=async(u,o)=>{await new Promise(r=>setTimeout(r,o.headers.Authorization.endsWith('alice')?10:0));return Response.json({rows:[{actor:o.headers.Authorization}],truncated:false})};
 const clients=['alice','bob'].map(token=>forRequest({baseUrl:'https://gateway.example.invalid',appId:'app-01',token,fetch}));
 const results=await Promise.all(clients.map(c=>c.queries.run('readiness@1.0.0',{})));
 assert.equal(results[0].rows[0].actor,'Bearer alice');assert.equal(results[1].rows[0].actor,'Bearer bob');
});
test('SDK exposes server Retry-After without automatic retries',async()=>{
 let calls=0;const c=forRequest({baseUrl:'https://gateway.example.invalid',appId:'app-01',token:'x',fetch:async()=>{calls++;return new Response('{"detail":"Budget exceeded"}',{status:429,headers:{'Retry-After':'17'}})}});
 await assert.rejects(()=>c.queries.run('readiness@1.0.0',{}),e=>e.status===429&&e.retryAfterSeconds===17);assert.equal(calls,1);
});
test('request cancellation is passed to the transport',async()=>{
 const controller=new AbortController();controller.abort();
 const c=forRequest({baseUrl:'https://gateway.example.invalid',appId:'app-01',token:'x',fetch:async(u,o)=>{assert.equal(o.signal.aborted,true);throw new DOMException('Aborted','AbortError')}});
 await assert.rejects(()=>c.queries.run('readiness@1.0.0',{}, {signal:controller.signal}),e=>e.name==='AbortError');
});
test('state path traversal is rejected before network access',()=>{
 const dc=createDreamcatcher({baseUrl:'http://localhost:8000',appId:'app-01',getToken:()=> 'x'});
 assert.throws(()=>dc.state.get('preferences','../other-app'));
 assert.throws(()=>createDreamcatcher({baseUrl:'http://localhost:8000',appId:'../other',getToken:()=> 'x'}));
});
test('telemetry contract permits only bounded event metadata',async()=>{
 let body;const dc=forRequest({baseUrl:'http://localhost:8000',appId:'app-01',token:'x',fetch:async(u,o)=>{body=JSON.parse(o.body);return new Response('{"ok":true}')}});
 await dc.events.emit('app.error','QUERY_FAILED');assert.deepEqual(body,{event:'app.error',code:'QUERY_FAILED'});
});
test('CLI validates and packages a synthetic uploaded app',async()=>{
 const files=await collect(new URL('../../examples/apps/build-readiness/',import.meta.url).pathname);
 const result=await validate(files);assert.equal(result.manifest.version,'1.0.0');
 const bytes=zip(files);assert.equal(bytes.readUInt32LE(0),0x04034b50);assert.ok(bytes.includes(Buffer.from('dreamcatcher.json')));
});
test('offline schema rejects permissive unknown fields and resource escalation',async()=>{
 const schema=JSON.parse(await readFile(new URL('../contracts/dreamcatcher.schema.json',import.meta.url)));
 assert.throws(()=>checkSchema({version:'1.0.0',admin:true},schema));
 assert.throws(()=>checkSchema({version:'1.0.0',runtime:{cpu:100}},schema));
 assert.throws(()=>checkSchema({version:'latest'},schema));
});
