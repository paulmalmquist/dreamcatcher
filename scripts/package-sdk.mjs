import {execFileSync} from 'node:child_process';
import {mkdirSync,renameSync} from 'node:fs';
import {resolve} from 'node:path';
mkdirSync('artifacts',{recursive:true});
const output=execFileSync(process.platform==='win32'?'npm.cmd':'npm',['pack','--workspace','sdk','--pack-destination','artifacts','--json'],{encoding:'utf8'});
const packed=JSON.parse(output)[0].filename;
renameSync(resolve('artifacts',packed),resolve('artifacts/dreamcatcher-sdk.tgz'));
console.log('SDK package ready');
