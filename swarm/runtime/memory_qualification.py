#!/usr/bin/python3 -I
"""Operator infrastructure turn on the authentic enrolled session; no node work."""
import fcntl
import json
import re
from pathlib import Path
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parent))
from sandbox import command, registration
from codex_rpc import CodexRPC

role = sys.argv[1]
assert role in {'developer', 'reviewer'}
label = sys.argv[2] if len(sys.argv)>2 else 'initial'
assert re.fullmatch(r'[a-z0-9-]{1,40}',label)
output_path=Path('/opt/loginom-worker/state')/('memory-qualification-'+role+('' if label=='initial' else '-'+label)+'.json')
if output_path.exists():raise SystemExit('Existing qualification receipt; choose an explicit new infrastructure check label')
lock = open('/opt/loginom-worker/state/heavy.lock', 'a')
fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
record = json.loads((Path('/etc/loginom-swarm/memory-roles') / (role+'.json')).read_text())
assert record['status'] == 'active'
row = registration('sampling', role)
argv, env = command(row, ['/opt/loginom-swarm/runtime/bin/codex', 'app-server', '--listen', 'stdio://'], network=True)
rpc = CodexRPC(argv, env)
try:
    response = rpc.request('thread/resume', {'threadId':record['threadId'], 'cwd':record['cwd'],
        'model':'gpt-6-astra', 'allowProviderModelFallback':False, 'approvalPolicy':'never', 'sandbox':'read-only'})
    assert response['thread']['id'] == record['threadId'] and response['model'] == 'gpt-6-astra'
    turn = rpc.request('turn/start', {'threadId':record['threadId'], 'model':'gpt-6-astra', 'effort':'medium',
        'input':[{'type':'text', 'text':
            'Инфраструктурная проверка общей памяти Loginom Swarm, SWARM_MEMORY_20260925. '
            'Подтверждённая настройка сервера: разработчик и независимый ревьювер используют отдельные '
            'постоянные сессии Codex на Astra medium и общий Peer основного проекта loginom-ai-agent. '
            'Приёмщик не получает память разработки. Исполнители размещены отдельной непривилегированной '
            'службой на VPS, поскольку вложенный Bubblewrap внутри Docker не прошёл проверку. '
            'Обработка Sampling ещё не разрешена: пользователь запустит её вручную после передачи. '
            'Не выполняй разработку, не вызывай инструменты и не меняй файлы. '
            'Ответь только SWARM_MEMORY_ACK_20260925.'}]})['turn']['id']
    deadline = time.monotonic()+150
    while not any(e['method']=='turn/completed' and e.get('turn',{}).get('id')==turn for e in rpc.events):
        if time.monotonic()>deadline:raise TimeoutError('Memory qualification turn unfinished')
        time.sleep(.2)
    detail = rpc.request('thread/read', {'threadId':record['threadId'], 'includeTurns':True})['thread']
    actual = next(t for t in detail['turns'] if t['id']==turn)
    assert actual['status']=='completed'
    assert all(i['type'] in {'userMessage','agentMessage','reasoning'} for i in actual['items'])
    assert any(i.get('text','').strip()=='SWARM_MEMORY_ACK_20260925' for i in actual['items'] if i['type']=='agentMessage')
    complete = {e['run']['eventName'] for e in rpc.events if e['method']=='hook/completed' and e['run']['status']=='completed'}
    assert {'sessionStart','userPromptSubmit','stop'} <= complete
    hook_log = [json.loads(line) for line in (Path(record['profile'])/'swarm-memory/hooks.jsonl').read_text().splitlines()]
    latest = {e['event']:e for e in hook_log if e['threadId']==record['threadId']}
    assert all(latest[event]['status']=='completed' for event in ['SessionStart','UserPromptSubmit','Stop'])
    receipt = {'role':role,'threadId':record['threadId'],'turnId':turn,'model':'gpt-6-astra',
               'events':rpc.events,'hooks':latest,'nodeStarted':False,'checkedAt':time.time(),
               'crossProjectReadbackVerified':False}
    path = output_path
    with path.open('x') as output:json.dump(receipt,output)
    path.chmod(0o600)
    print(json.dumps({'role':role,'threadId':record['threadId'],'captureCommit':'passed','nodeStarted':False}))
finally:
    rpc.close()
