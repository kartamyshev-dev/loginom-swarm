#!/usr/bin/env python3
"""Prepare visible role records without giving them a runnable adapter or timer."""
import importlib.util
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('api',ROOT/'swarm/scripts/paperclip-api.py')
api=importlib.util.module_from_spec(spec);spec.loader.exec_module(api)
config=ROOT/'swarm/config/campaign.json';cfg=json.loads(config.read_text())
roles={
 'reviewer':('Swarm reviewer','Независимое ревью закреплённого commit. Рабочая копия только для чтения. Astra medium. Никаких push, merge или изменения эталона.'),
 'acceptance':('Swarm acceptance','Приёмка полной CLI-сборки через Sol low. Только бизнес-ТЗ и исходные данные. Без памяти разработки и ожидаемых результатов. PASS устанавливает координатор после независимой проверки результатов, save/reopen и cleanup.'),
}
c=api.Client()
try:
 agents=c.request('GET',f'/api/companies/{cfg["companyId"]}/agents')
 ids={}
 for role,(name,description) in roles.items():
  matches=[a for a in agents if (a.get('metadata') or {}).get('swarmRole')==role]
  if len(matches)>1:raise RuntimeError('Ambiguous Swarm role')
  if matches:
   agent=matches[0]
  else:
   agent=c.request('POST',f'/api/companies/{cfg["companyId"]}/agents',{
    'name':name,'role':'general','title':'Подготовка — запуск закрыт',
    'capabilities':description,
    'adapterType':'process','adapterConfig':{'command':'/usr/bin/false','cwd':'/tmp','timeoutSec':60},
    'runtimeConfig':{'heartbeat':{'enabled':False,'wakeOnDemand':False,'maxConcurrentRuns':1}},
    'permissions':{'canCreateAgents':False,'canCreateSkills':False},
    'metadata':{'swarmRole':role,'setupStatus':'incomplete','execution':'unprivileged-host-service','model':cfg['models'][role]},
    'instructionsBundle':{'entryFile':'AGENTS.md','files':{'AGENTS.md':
       '# Loginom Swarm: '+role+'\n\n'+description+'\n\nСистема ещё не допущена к обработке узлов. Не запускайте Sampling. '
       'Расписания и автоматические пробуждения выключены. Результат неизвестной мутации или cleanup означает blocked; '
       'не удаляйте locks по возрасту, не повторяйте мутацию автоматически.\n'}}})
  if agent.get('status')!='paused':c.request('POST',f'/api/agents/{agent["id"]}/pause',{})
  ids[role]=agent['id']
 # The existing developer identity and old SSH pilot are retained until complete replacement.
 cfg['agentIds']={'developer':'c49d36f3-1b4d-4f09-8184-acc73daef2c5',**ids,'publisher':cfg['publisherAgentId']}
 config.write_text(json.dumps(cfg,indent=2,ensure_ascii=False)+'\n')
 print(json.dumps({'roles':ids,'paused':True,'executionStarted':False}))
finally:c.close()
