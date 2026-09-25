#!/usr/bin/python3 -I
"""Recheck an existing build with its upstream manifest verifier, without rebuilding."""
import fcntl
import json
import subprocess
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from sandbox import command,registration

lock=open('/opt/loginom-worker/state/heavy.lock','a')
fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
record=registration('infrastructure','developer')
base=record['workspace']
source=base+'/source/packages/loginom-host/src/cli-manifest.ts'
artifact=base+'/cli-candidate'
script='import {verifyCliManifest} from '+json.dumps(source)+'; const m=await verifyCliManifest('+json.dumps(artifact)+', {platform:"linux",arch:"x64"}); if(m.sourceCommit!=="f81ebded7333ae7d974fdc5f87e8864cf75dd9c7"||m.sourceDirty)throw Error("source mismatch"); console.log(JSON.stringify(m));'
a,e=command(record,['/opt/loginom-swarm/runtime/bin/bun','-e',script])
p=subprocess.run(a,env=e,capture_output=True,text=True,timeout=180)
if p.returncode:raise RuntimeError('Candidate manifest verification failed')
m=json.loads(p.stdout)
result={'manifestVerified':True,'sourceCommit':m['sourceCommit'],'sourceDirty':m['sourceDirty'],'version':m['version'],'dependencies':m['dependencies']}
Path('/opt/loginom-worker/state/cli-candidate-verified.json').write_text(json.dumps(result)+'\n')
print(json.dumps(result))
