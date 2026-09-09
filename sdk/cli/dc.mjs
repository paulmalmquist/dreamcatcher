#!/usr/bin/env node
import {mkdir,cp,writeFile,readFile} from 'node:fs/promises';
import {resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {collect,validate,zip} from './source.mjs';

async function api(path,body){
 const base=new URL(process.env.DC_GATEWAY_ORIGIN??'http://localhost:8000');
 if(base.username||base.password||base.search||base.hash||base.pathname!=='/'||base.protocol!=='https:'&&!(base.protocol==='http:'&&['localhost','127.0.0.1','[::1]'].includes(base.hostname)))throw Error('Set a trusted HTTPS DC_GATEWAY_ORIGIN (loopback HTTP allowed)');
 if(!process.env.DC_DEVELOPER_TOKEN)throw Error('Create a one-hour developer token in the app control panel; set DC_DEVELOPER_TOKEN in this terminal only');
 const r=await fetch(new URL('/api/v2'+path,base),{method:body?'POST':'GET',headers:{Authorization:'Bearer '+process.env.DC_DEVELOPER_TOKEN},body,redirect:'error',signal:AbortSignal.timeout(35000)});
 const result=await r.json();if(!r.ok)throw Error(JSON.stringify(result.detail??result));return result;
}
async function main(){
 const [command,target='.',output='source.zip']=process.argv.slice(2);
 if(command==='init'){
  if(target==='.')throw Error('Choose a new directory: dc init my-dashboard');
  const dir=resolve(target);await mkdir(dir);await cp(fileURLToPath(new URL('../templates/dashboard/',import.meta.url)),dir,{recursive:true,errorOnExist:true,force:false});
  console.log('Created '+dir+'\nRead README.md. Install the downloaded SDK package to generate your lockfile.');return;
 }
 if(command==='schema'){console.log(await readFile(new URL('../contracts/dreamcatcher.schema.json',import.meta.url),'utf8'));return}
 if(command==='status'){
  if(!/^[a-zA-Z0-9-]{2,80}$/.test(target))throw Error('dc status APP_ID');
  console.log(JSON.stringify(await api('/apps/'+target+'/overview'),null,2));return;
 }
 if(['validate','pack','submit'].includes(command)){
  const files=await collect(target),result=await validate(files);
  if(command==='validate'){console.log(JSON.stringify(result,null,2));return}
  const archive=zip(files);if(archive.length>8*1024*1024)throw Error('ZIP exceeds upload limit');
  if(command==='pack'){await writeFile(resolve(output),archive,{flag:'wx'});console.log('Wrote '+resolve(output));return}
  const app=process.env.DC_APP_ID;if(!app||!/^[a-zA-Z0-9-]{2,80}$/.test(app))throw Error('Set DC_APP_ID to the hosted app ID');
  const form=new FormData();form.append('file',new Blob([archive]),'source.zip');console.log(JSON.stringify(await api('/apps/'+app+'/submissions',form),null,2));return;
 }
 console.log('Dreamcatcher SDK 2\n  dc init NEW_DIRECTORY\n  dc validate SOURCE_DIRECTORY\n  dc pack SOURCE_DIRECTORY OUTPUT.zip\n  dc submit SOURCE_DIRECTORY\n  dc status APP_ID\n  dc schema\n\nUpload never bypasses independent release review.');
 if(command)process.exitCode=1;
}
main().catch(e=>{console.error(e.message);process.exitCode=1});
