#!/usr/bin/python3 -I
"""Read-only MCP proof through the role's pinned Codex and real resumed thread."""
import fcntl
import json
from pathlib import Path
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parent))
from codex_rpc import CodexRPC
from sandbox import command,registration

role=sys.argv[1]
assert role in {'developer','reviewer'}
lock=open('/opt/loginom-worker/state/heavy.lock','a')
fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
record=json.loads((Path('/etc/loginom-swarm/memory-roles')/(role+'.json')).read_text())
argv,env=command(registration('sampling',role),['/opt/loginom-swarm/runtime/bin/codex','app-server','--listen','stdio://'],network=True)
rpc=CodexRPC(argv,env)
uri=record['memoryUri']+'/events/2026/09/25/swarm_memory_acknowledge.md'
try:
    resumed=rpc.request('thread/resume',{'threadId':record['threadId'],'cwd':record['cwd'],
        'model':'gpt-6-astra','allowProviderModelFallback':False,'approvalPolicy':'never','sandbox':'read-only'})
    assert resumed['thread']['id']==record['threadId'] and resumed['model']=='gpt-6-astra'
    inventory=rpc.request('mcpServerStatus/list',{'threadId':record['threadId'],'detail':'toolsAndAuthOnly'})
    server=next(s for s in inventory['data'] if s['name']=='swarm_openviking')
    assert {t['name'] for t in server['tools'].values()}=={'find','read'} and not server.get('toolsError')
    def call(name,args):
        result=rpc.request('mcpServer/tool/call',{'threadId':record['threadId'],
            'server':'swarm_openviking','tool':name,'arguments':args},timeout=65)
        # Pinned app-server wraps the MCP CallToolResult.
        return result.get('result',result)
    found=call('find',{'query':'SWARM_MEMORY_20260925 shared Loginom Swarm memory','limit':1})
    assert not found.get('isError') and 'viking://' in json.dumps(found)
    read=call('read',{'uri':uri})
    assert not read.get('isError') and 'SWARM_MEMORY_20260925' in json.dumps(read)
    rejected=call('read',{'uri':'viking://user/other/memories/private.md'})
    assert rejected.get('isError') is True
    hooks=rpc.request('hooks/list',{'cwds':[record['cwd']]})['data'][0]
    assert not hooks['errors'] and not hooks['warnings'] and len(hooks['hooks'])==5
    assert all(h['trustStatus']=='trusted' for h in hooks['hooks'])
    receipt={'role':role,'threadId':record['threadId'],'tools':['find','read'],
             'searchPassed':True,'readPassed':True,'foreignPeerRejected':True,
             'hooksStillTrusted':True,'uri':uri,'nodeStarted':False,'checkedAt':time.time()}
    path=Path('/opt/loginom-worker/state')/('memory-tools-'+role+'.json')
    path.write_text(json.dumps(receipt)+'\n');path.chmod(0o600)
    print(json.dumps(receipt))
finally:rpc.close()
