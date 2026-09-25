#!/usr/bin/python3 -I
"""One explicit infrastructure attempt on supported import/grouping, never Sampling."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from sandbox import command,registration
from loginom_account import AccountLease

lock=open('/opt/loginom-worker/state/heavy.lock','a')
fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
record=registration('sampling','acceptance')
profile=Path(record['profile']);workspace=Path(record['workspace'])
if (profile/'.writer').exists():raise SystemExit('CLI writer needs reconciliation')
output=Path('/opt/loginom-worker/state/cli-infrastructure-v1')
if output.exists():raise SystemExit('This attempt already exists; inspect it instead of retrying')
fixtures=Path('/opt/loginom-swarm/qualification/loginom-infrastructure')
artifact=Path('/opt/loginom-worker/.local/share/loginom-ai-agent-cli/0.1.16-prod')
exe=artifact/'bin/loginom-ai-agent-cli'
args,env=command(record,[str(exe),'--version'])
version=subprocess.check_output(args,env=env,text=True,timeout=30).strip()
if version!='0.1.16':raise SystemExit('CLI version differs from infrastructure baseline')
if any(workspace.iterdir()):raise SystemExit('Acceptance workspace is not empty')
account=AccountLease('/opt/loginom-worker/state','cli-infrastructure-v1')
output.mkdir(mode=0o700)
hashes={}
for name in ['task.md','data.csv']:
    data=(fixtures/name).read_bytes()
    (workspace/name).write_bytes(data)
    hashes[name]=hashlib.sha256(data).hexdigest()
shutil.copyfile(fixtures/'oracle.json',output/'oracle.json')
payload=['/usr/bin/xvfb-run','-a',str(exe),'run','--no-headless','--format','json',
    '--model','openai/gpt-6-sol','--variant','low','--dir',str(workspace),
    '--file',str(workspace/'task.md'),'--file',str(workspace/'data.csv'),
    '--','Выполни приложенное задание и сохрани результат в указанном в нём новом пакете.']
args,env=command(record,payload,network=True)
spec={'argv':args,'env':env,'output':str(output),
      'redactor':str(artifact/'resources/loginom/runtime/client/lib/redact.mjs'),
      'connection':str(profile/'loginom/connection/connection.json')}
spec_path=output/'observer.json';spec_path.write_text(json.dumps(spec));spec_path.chmod(0o600)
manifest={'kind':'infrastructure-only','artifactVersion':version,'model':'openai/gpt-6-sol',
          'variant':'low','inputSha256':hashes,'expectedVisibleToModel':False,'state':'admitted','nodeStarted':False}
(output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
try:
    result=subprocess.run(['/opt/loginom-swarm/runtime/bin/node','/opt/loginom-swarm/runtime/cli_observer.mjs',str(spec_path)])
finally:
    account.close()
manifest['state']='awaiting-independent-audit' if result.returncode==0 else 'blocked'
manifest['observerExitCode']=result.returncode
(output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
raise SystemExit(result.returncode)
