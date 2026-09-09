import {readFile,readdir,lstat} from 'node:fs/promises';
import {resolve,join} from 'node:path';
import {createHash} from 'node:crypto';

export async function collect(directory){
 const root=resolve(directory),files=new Map();let total=0;
 async function walk(dir,prefix=''){
  for(const entry of (await readdir(dir)).sort()){
   if(['node_modules','.git','.venv','__pycache__','source.zip'].includes(entry))continue;
   if(entry==='.env'||entry.startsWith('.env.')&&entry!=='.env.example')throw Error('Remove credentials from source: '+entry);
   const name=prefix+entry,path=join(dir,entry),info=await lstat(path);
   if(info.isSymbolicLink())throw Error('Source symlinks are not allowed');
   if(info.isDirectory()){await walk(path,name+'/');continue}
   if(!info.isFile()||info.size>1024*1024)throw Error('Source file limit exceeded: '+name);
   const data=await readFile(path);total+=data.length;
   if(total>8*1024*1024||files.size>=500)throw Error('Source bundle limits exceeded');
   if(/-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|(?:sk-proj-|ghp_)[A-Za-z0-9_-]{20,}/.test(data.toString()))throw Error('Potential secret: '+name);
   files.set(name,data);
  }
 }
 await walk(root);return files;
}

export function checkSchema(value,schema,root=schema,path='$'){
 if(schema.$ref)return checkSchema(value,root.$defs[schema.$ref.split('/').at(-1)],root,path);
 if(schema.anyOf){if(schema.anyOf.some(s=>{try{checkSchema(value,s,root,path);return true}catch{return false}}))return;throw Error(path+': no schema variant matched')}
 if(schema.const!==undefined&&value!==schema.const)throw Error(path+': unsupported value');
 if(schema.enum&&!schema.enum.includes(value))throw Error(path+': unsupported enum');
 const type=schema.type;
 const matches=type==='object'?value!==null&&typeof value==='object'&&!Array.isArray(value):type==='array'?Array.isArray(value):type==='integer'?Number.isInteger(value):type==='number'?typeof value==='number'&&Number.isFinite(value):type==='null'?value===null:typeof value===type;
 if(type&&!matches)throw Error(path+': expected '+type);
 if(type==='object'){
  for(const k of schema.required??[])if(!(k in value))throw Error(path+'.'+k+': required');
  for(const [k,v] of Object.entries(value)){const rule=schema.properties?.[k];if(rule)checkSchema(v,rule,root,path+'.'+k);else if(schema.additionalProperties===false)throw Error(path+'.'+k+': unknown field');else if(typeof schema.additionalProperties==='object')checkSchema(v,schema.additionalProperties,root,path+'.'+k)}
 }
 if(type==='array'){if(value.length<(schema.minItems??0)||value.length>(schema.maxItems??Infinity))throw Error(path+': array size');value.forEach((v,i)=>checkSchema(v,schema.items,root,path+'['+i+']'))}
 if(type==='string'){if(value.length<(schema.minLength??0)||value.length>(schema.maxLength??Infinity)||schema.pattern&&!new RegExp(schema.pattern).test(value))throw Error(path+': string contract')}
 if((type==='integer'||type==='number')&&(value<(schema.minimum??-Infinity)||value>(schema.maximum??Infinity)))throw Error(path+': numeric bounds');
}

export async function validate(files){
 if(!files.has('dreamcatcher.json')||!files.has('Dockerfile'))throw Error('dreamcatcher.json and Dockerfile are required');
 const manifest=JSON.parse(files.get('dreamcatcher.json'));
 const schema=JSON.parse(await readFile(new URL('../contracts/dreamcatcher.schema.json',import.meta.url)));
 checkSchema(manifest,schema);
 if((manifest.runtime?.web??'spa')==='spa'&&!(manifest.runtime?.entrypoint??'dist/index.html').endsWith('/index.html'))throw Error('SPA contract requires index.html');
 for(const list of [manifest.queries??[],manifest.skills??[]])if(new Set(list).size!==list.length||list.some(x=>!/^[a-z][a-z0-9-]{1,63}@\d+\.\d+\.\d+(?:-[a-z0-9.-]+)?$/.test(x)))throw Error('Unique exact query/skill references required');
 if(files.has('package.json')&&!files.has('package-lock.json'))throw Error('Run npm install with the downloaded SDK to create a package-lock.json');
 return {manifest,source_files:files.size,sha256:Object.fromEntries([...files].map(([p,b])=>[p,createHash('sha256').update(b).digest('hex')])),note:'Static validation only. Trusted build, governance and independent review are still required.'};
}

function crc32(buf){let crc=0xffffffff;for(const b of buf){crc^=b;for(let i=0;i<8;i++)crc=(crc>>>1)^(crc&1?0xedb88320:0)}return (crc^0xffffffff)>>>0}
export function zip(files){
 // ZIP STORE: deterministic source bytes, no dependencies or external shell tools.
 const local=[],central=[];let offset=0;
 for(const [path,data] of [...files].sort(([a],[b])=>a.localeCompare(b))){
  const name=Buffer.from(path),crc=crc32(data),h=Buffer.alloc(30),c=Buffer.alloc(46);
  h.writeUInt32LE(0x04034b50);h.writeUInt16LE(20,4);h.writeUInt16LE(0x800,6);h.writeUInt16LE(33,12);h.writeUInt32LE(crc,14);h.writeUInt32LE(data.length,18);h.writeUInt32LE(data.length,22);h.writeUInt16LE(name.length,26);
  c.writeUInt32LE(0x02014b50);c.writeUInt16LE(20,4);c.writeUInt16LE(20,6);c.writeUInt16LE(0x800,8);c.writeUInt16LE(33,14);c.writeUInt32LE(crc,16);c.writeUInt32LE(data.length,20);c.writeUInt32LE(data.length,24);c.writeUInt16LE(name.length,28);c.writeUInt32LE(offset,42);
  local.push(h,name,data);central.push(c,name);offset+=h.length+name.length+data.length;
 }
 const directory=Buffer.concat(central),end=Buffer.alloc(22);end.writeUInt32LE(0x06054b50);end.writeUInt16LE(files.size,8);end.writeUInt16LE(files.size,10);end.writeUInt32LE(directory.length,12);end.writeUInt32LE(offset,16);
 return Buffer.concat([...local,directory,end]);
}
