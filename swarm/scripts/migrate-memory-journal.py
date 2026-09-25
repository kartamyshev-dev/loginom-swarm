#!/usr/bin/python3 -I
"""One-time verified v1→v2 transport migration. Requires stopped gateway/worker."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

assert os.geteuid()==0
lock=open('/opt/loginom-worker/state/heavy.lock','a')
fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
for unit in ['loginom-swarm-memory','loginom-swarm-worker']:
    assert subprocess.run(['systemctl','is-active','--quiet',unit]).returncode!=0
staged=[]
for role in ['developer','reviewer']:
    record=json.loads((Path('/etc/loginom-swarm/memory-roles')/(role+'.json')).read_text())
    path=Path('/var/lib/loginom-swarm-memory')/(record['threadId']+'.json')
    old=json.loads(path.read_text())
    if old.get('schema')==2:continue
    assert old['state']=='completed'
    route='/api/v1/sessions/cx-'+record['threadId']+'/commit'
    digest=hashlib.sha256(json.dumps(['POST',route,{'telemetry':False}],sort_keys=True).encode()).hexdigest()
    assert old['digest']==digest and old['result'].get('status')!='error'
    receipt=json.loads((Path('/opt/loginom-worker/state')/('memory-qualification-'+role+'.json')).read_text())
    state_path=Path(record['profile'])/'swarm-memory'/(record['threadId']+'.json')
    state=json.loads(state_path.read_text())
    offset=state['capturedTurnCount']
    assert receipt['threadId']==record['threadId'] and receipt['hooks']['Stop']['status']=='completed'
    assert offset==receipt['hooks']['Stop']['cursor']
    assert not state_path.with_suffix('.lock').exists()
    staged.append((path,old,offset,state_path,state))
for path,old,offset,state_path,state in staged:
    backup=path.with_suffix('.legacy-v1.json')
    assert not backup.exists()
    shutil.copy2(path,backup)
    info=path.stat();os.chown(backup,info.st_uid,info.st_gid)
    journal={'schema':2,'nextOffset':offset,'entries':{'commit:'+str(offset):old}}
    path.write_text(json.dumps(journal)+'\n')
    state['swarmCommittedCursor']=offset
    state_path.write_text(json.dumps(state)+'\n')
print(json.dumps({'migratedJournals':len(staged),'source':'completed commit digest and matching native Stop cursor'}))
