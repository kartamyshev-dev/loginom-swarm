#!/usr/bin/python3
"""Root preparation only. Does not invent thread IDs or activate memory access."""
import hashlib
import json
import os
from pathlib import Path
import pwd
import secrets

user=pwd.getpwnam('loginom-worker')
assert os.geteuid()==0
root=Path('/etc/loginom-swarm/memory-roles');root.mkdir(mode=0o755,exist_ok=True);root.chmod(0o755)
config_path=Path('/etc/loginom-swarm/memory-gateway.json')
gateway=json.loads(config_path.read_text())
for role in ['developer','reviewer']:
 profile=Path('/opt/loginom-worker/profiles/sampling')/role
 cwd='/opt/loginom-worker/workspaces/sampling/'+role
 record_path=root/(role+'.json')
 hooks_path=profile/'hooks.json'
 if record_path.exists() or hooks_path.exists():raise RuntimeError('Existing role preparation: reconcile before retry')
 token=secrets.token_urlsafe(40);digest=hashlib.sha256(token.encode()).hexdigest()
 record={'generation':'20260925.1','role':role,'cwd':cwd,'profile':str(profile),'status':'pending','threadId':None,
         'peer':'-Users-kartamyshev-Git-loginom-ai-agent',
         'memoryUri':'viking://user/kartamyshev/peers/-Users-kartamyshev-Git-loginom-ai-agent/memories'}
 directory=profile/'.openviking';directory.mkdir(mode=0o700,exist_ok=True);os.chown(directory,user.pw_uid,user.pw_gid)
 connection=directory/'ovcli.conf';connection.write_text(json.dumps({'url':'http://127.0.0.1:8766','api_key':token})+'\n');connection.chmod(0o600);os.chown(connection,user.pw_uid,user.pw_gid)
 hooks={'hooks':{event:[{'hooks':[{'type':'command','command':f'/opt/loginom-swarm/runtime/bin/node /opt/loginom-swarm/memory/hook.mjs {role} {event}','timeout':3 if event=='SessionEnd' else 60}]}] for event in ['SessionStart','UserPromptSubmit','Stop','PreCompact','SessionEnd']}}
 hooks_path.write_text(json.dumps(hooks,indent=2)+'\n');hooks_path.chmod(0o644)
 record['hooksSha256']=hashlib.sha256(hooks_path.read_bytes()).hexdigest()
 record_path.write_text(json.dumps(record,indent=2)+'\n');record_path.chmod(0o644)
 gateway['principals'][digest]={k:record[k] for k in ['role','peer','status','threadId']}
config_path.write_text(json.dumps(gateway)+'\n')
print(json.dumps({'preparedRoles':['developer','reviewer'],'activePrincipals':0,'threadIdsCreated':False}))
