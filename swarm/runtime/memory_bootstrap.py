#!/usr/bin/python3 -I
"""Operator-only real session/bootstrap observer. Does not grant memory access."""
import hashlib
import json
import os
from pathlib import Path
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parent))
from sandbox import command,registration
from codex_rpc import CodexRPC

role=sys.argv[1]
if role not in {'developer','reviewer'}:raise SystemExit('Invalid role')
record=json.loads((Path('/etc/loginom-swarm/memory-roles')/(role+'.json')).read_text())
if record['status']!='pending':raise SystemExit('Only pending enrollment can bootstrap')
output=Path('/opt/loginom-worker/state')/('memory-bootstrap-'+role+'.json')
if output.exists():raise SystemExit('Existing bootstrap receipt; inspect before resuming')
row=registration('sampling',role)
argv,env=command(row,['/opt/loginom-swarm/runtime/bin/codex','app-server','--listen','stdio://'],network=True)
rpc=CodexRPC(argv,env)
try:
 def hooks():
  result=rpc.request('hooks/list',{'cwds':[record['cwd']]})
  if len(result['data'])!=1:raise RuntimeError('Wrong hook inventory')
  entry=result['data'][0]
  if entry['errors'] or entry['warnings']:raise RuntimeError('Hook inventory is not clean')
  found=entry['hooks']
  if len(found)!=5:raise RuntimeError('Exactly five isolated memory hooks required')
  expected=json.loads((Path(record['profile'])/'hooks.json').read_text())
  if hashlib.sha256((Path(record['profile'])/'hooks.json').read_bytes()).hexdigest()!=record['hooksSha256']:
   raise RuntimeError('Hook definitions changed')
  commands={g['hooks'][0]['command'] for groups in expected['hooks'].values() for g in groups}
  if {h.get('command') for h in found}!=commands or any(not h['enabled'] or h['source']!='user' or h['isManaged'] for h in found):
   raise RuntimeError('Hooks differ from reviewed role definitions')
  return found
 before=hooks()
 rpc.request('config/batchWrite',{'edits':[{'keyPath':'hooks.state','value':{h['key']:{'trusted_hash':h['currentHash'],'enabled':True} for h in before},'mergeStrategy':'upsert'}],
                                 'filePath':None,'expectedVersion':None,'reloadUserConfig':False})
 trusted=hooks()
 if any(h['trustStatus']!='trusted' for h in trusted):raise RuntimeError('Hook trust not confirmed')
 observed_path=Path(record['profile'])/'swarm-memory/bootstrap.json'
 previous=json.loads(observed_path.read_text()) if observed_path.exists() else None
 method='thread/resume' if previous else 'thread/start'
 identity={'threadId':previous['threadId']} if previous else {}
 response=rpc.request(method,{**identity,'cwd':record['cwd'],'model':'gpt-6-astra','allowProviderModelFallback':False,
   'approvalPolicy':'never','sandbox':'read-only','config':{'model_reasoning_effort':'medium'}})
 thread=response['thread']['id']
 if response.get('model')!='gpt-6-astra':raise RuntimeError('Exact model unavailable')
 turn=rpc.request('turn/start',{'threadId':thread,'model':'gpt-6-astra','effort':'medium',
   'input':[{'type':'text','text':'Инфраструктурная проверка регистрации памяти. Не выполняй разработку, не вызывай инструменты и не меняй файлы. Ответь только SWARM_BOOTSTRAP_OK.'}]})
 turn_id=turn['turn']['id'];deadline=time.monotonic()+120
 while not any(e.get('turn',{}).get('id')==turn_id and e['method']=='turn/completed' for e in rpc.events):
  if time.monotonic()>deadline:raise TimeoutError('Bootstrap turn unfinished')
  time.sleep(.2)
 completed=next(e for e in rpc.events if e.get('turn',{}).get('id')==turn_id and e['method']=='turn/completed')
 if completed['turn']['status']!='completed':raise RuntimeError('Bootstrap model failed')
 detail=rpc.request('thread/read',{'threadId':thread,'includeTurns':True})['thread']
 actual=next(t for t in detail['turns'] if t['id']==turn_id)
 if any(i['type'] not in {'userMessage','agentMessage','reasoning'} for i in actual['items']):raise RuntimeError('Bootstrap used a tool')
 if not any(i.get('text','').strip()=='SWARM_BOOTSTRAP_OK' for i in actual['items'] if i['type']=='agentMessage'):
  raise RuntimeError('Bootstrap response differs')
 observed=json.loads((Path(record['profile'])/'swarm-memory/bootstrap.json').read_text())
 if observed['threadId']!=thread or observed['cwd']!=record['cwd']:raise RuntimeError('No authentic SessionStart observation')
 receipt={'generation':record['generation'],'role':role,'threadId':thread,'turnId':turn_id,'turnStatus':'completed',
  'cwd':record['cwd'],'model':response['model'],'effort':'medium','developmentStarted':False,'observedSessionStart':observed,
  'hooks':[{'key':h['key'],'currentHash':h['currentHash'],'trustStatus':h['trustStatus'],'eventName':h['eventName']} for h in trusted],
  'events':rpc.events,'checkedAt':time.time()}
 with output.open('x') as file:json.dump(receipt,file)
 output.chmod(0o600)
 print(json.dumps({k:receipt[k] for k in ['role','threadId','turnStatus','model','developmentStarted']}))
finally:rpc.close()
