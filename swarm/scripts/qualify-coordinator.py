#!/usr/bin/env python3
"""Run fixed sandbox probes through real native cases; never processes Sampling."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'swarm/runtime'))
from coordinator import Coordinator
spec=importlib.util.spec_from_file_location('api',ROOT/'swarm/scripts/paperclip-api.py')
api=importlib.util.module_from_spec(spec);spec.loader.exec_module(api)
cfg=json.loads((ROOT/'swarm/config/campaign.json').read_text())


def worker(method,path,payload=None):
 p=subprocess.run([str(ROOT/'swarm/scripts/server.sh'),'-o','PreferredAuthentications=password','-o','PubkeyAuthentication=no',
                   'python3 -I /opt/loginom-swarm/runtime/worker-rpc.py'],
                  input=json.dumps({'method':method,'path':path,'payload':payload}),text=True,capture_output=True,timeout=30)
 if p.returncode:raise RuntimeError('Worker RPC failed; read native case/receipt before retry')
 return json.loads(p.stdout)


c=api.Client()
try:
 rows=c.request('GET',f'/api/companies/{cfg["companyId"]}/pipelines')
 pipelines=[r.get('pipeline',r) for r in rows]
 matches=[p for p in pipelines if p['key']=='swarm-infrastructure']
 if len(matches)>1:raise RuntimeError('Ambiguous infrastructure pipeline')
 p=matches[0] if matches else c.request('POST',f'/api/companies/{cfg["companyId"]}/pipelines',{
  'key':'swarm-infrastructure','name':'Swarm — проверка протокола','projectId':cfg['projectId'],
  'description':'Только проверки sandbox. Модели и обработка узлов не запускаются.', 'enforceTransitions':True,
  'stages':[{'key':key,'name':name,'kind':kind,'position':i*100} for i,(key,name,kind) in enumerate([
   ('developer','Проверка среды разработчика','working'),('reviewer','Проверка среды ревьювера','working'),
   ('acceptance','Проверка среды приёмщика','working'),('done','Проверки завершены','done'),
   ('blocked','Нужен разбор','working'),('cancelled','Отменено','cancelled')])]})
 pid=p['id']
 edges=[('developer','reviewer'),('reviewer','acceptance'),('acceptance','done')]
 for stage in ['developer','reviewer','acceptance']:edges +=[(stage,'blocked'),(stage,'cancelled')]
 current=c.request('GET','/api/pipelines/'+pid)
 if not current['transitions']:
  c.request('PUT','/api/pipelines/'+pid+'/transitions',{'enforceTransitions':True,'transitions':[{'fromStageKey':a,'toStageKey':b} for a,b in edges]})
 cases=c.request('GET','/api/pipelines/'+pid+'/cases')
 matches=[r['case'] for r in cases if r['case'].get('caseKey')=='protocol-v1']
 if len(matches)>1:raise RuntimeError('Ambiguous diagnostic case')
 case=matches[0] if matches else c.request('POST','/api/pipelines/'+pid+'/cases',{
  'caseKey':'protocol-v1','title':'Диагностика протокола v1 — без моделей',
  'stageKey':'developer','fields':{'purpose':'infrastructure-protocol'}})['case']
 coordinator=Coordinator(c,worker,pid)
 for _ in range(15):
  result=coordinator.tick(case['id'])
  print(json.dumps(result),flush=True)
  if result['stage'] in {'done','blocked','cancelled'}:
   if result['stage']!='done':raise RuntimeError('Infrastructure qualification did not pass')
   break
  time.sleep(.2)
 else:raise RuntimeError('Qualification needs another read-only inspection; no blind retry')
 receipt={'pipelineId':pid,'caseId':case['id'],'stage':result['stage'],'nodeStarted':False}
 dest=ROOT/'private/coordinator-qualification.json';dest.write_text(json.dumps(receipt)+'\n');dest.chmod(0o600)
finally:c.close()
