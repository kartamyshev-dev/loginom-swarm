// Operator-only subprocess observer. No raw CLI output is ever written to disk.
import {spawn} from 'node:child_process';
import {readFileSync,writeFileSync,appendFileSync,statfsSync} from 'node:fs';
import {join} from 'node:path';
import {pathToFileURL} from 'node:url';

const spec=JSON.parse(readFileSync(process.argv[2],'utf8'));
const {createRedactor}=await import(pathToFileURL(spec.redactor).href);
const redactor=createRedactor();
redactor.prime(JSON.parse(readFileSync(spec.connection,'utf8')));
const output=spec.output;
const started=Date.now();let minimumMemory=Infinity,minimumDisk=Infinity,reason=null,stderrBytes=0,omitted=0,sessionID=null;
const allowed=new Set(['tool_use','text','step_start','step_finish','error']);
const sample=()=>{
 const match=readFileSync('/proc/meminfo','utf8').match(/^MemAvailable:\s+(\d+)/m);
 const memory=Number(match?.[1])/1024;
 const fs=statfsSync('/opt/loginom-worker');const disk=fs.bavail*fs.bsize/1024**3;
 minimumMemory=Math.min(minimumMemory,memory);minimumDisk=Math.min(minimumDisk,disk);
 return memory>=512 && disk>=20;
};
if(!sample())throw new Error('Resource admission failed');
const child=spawn(spec.argv[0],spec.argv.slice(1),{env:spec.env,stdio:['ignore','pipe','pipe'],detached:true});
writeFileSync(join(output,'process.json'),JSON.stringify({pid:child.pid,startedAt:started,state:'running'}),{mode:0o600});
let buffer='';let discarding=false;
function line(value){
 try{
  const event=JSON.parse(value);
  if(!allowed.has(event.type)||event.part?.type==='reasoning'){omitted++;return;}
  if(typeof event.sessionID==='string')sessionID=event.sessionID;
  appendFileSync(join(output,'events.jsonl'),JSON.stringify(redactor.redact(event))+'\n',{mode:0o600});
 }catch{omitted++;}
}
child.stdout.setEncoding('utf8');
child.stdout.on('data',chunk=>{
 for(const part of chunk.split(/(?<=\n)/)){
  if(!discarding)buffer+=part;
  if(buffer.length>2*1024*1024){buffer='';discarding=true;omitted++;}
  if(part.endsWith('\n')){if(!discarding)line(buffer);buffer='';discarding=false;}
 }
});
// stderr can contain arbitrary provider diagnostics. Keep only its size.
child.stderr.on('data',chunk=>{stderrBytes+=chunk.length;});
let interruptedAt=null;
function interrupt(why){
 if(!reason){reason=why;interruptedAt=Date.now();}
 try{process.kill(-child.pid,Date.now()-interruptedAt>15000?'SIGKILL':'SIGINT');}catch{}
}
process.on('SIGINT',()=>interrupt('operator_cancelled'));
process.on('SIGTERM',()=>interrupt('operator_cancelled'));
const timer=setInterval(()=>{
 if(!sample())interrupt('resource_floor');
 if(Date.now()-started>1800000)interrupt('deadline');
 if(reason)interrupt(reason);
},1000);
const exit=await new Promise(resolve=>{
 child.on('error',()=>resolve({code:null,signal:null,spawnFailed:true}));
 child.on('close',(code,signal)=>resolve({code,signal}));
});
clearInterval(timer);if(buffer&&!discarding)line(buffer);sample();
const receipt={...exit,reason,sessionID,elapsedSeconds:(Date.now()-started)/1000,
 minimumAvailableMiB:minimumMemory,minimumFreeGiB:minimumDisk,stderrBytes,omittedEvents:omitted,
 result:'CLI_FINISHED_REQUIRES_INDEPENDENT_AUDIT',cleanupConfirmed:false,nodeStarted:false};
writeFileSync(join(output,'exit.json'),JSON.stringify(receipt,null,2)+'\n',{mode:0o600});
console.log(JSON.stringify(receipt));
process.exitCode=exit.code===0&&!reason?0:1;
