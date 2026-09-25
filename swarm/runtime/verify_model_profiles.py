#!/usr/bin/python3 -I
"""Infrastructure-only auth and browser checks inside the final role sandbox."""
import fcntl
import json
import subprocess
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from sandbox import command,registration

lock=open('/opt/loginom-worker/state/heavy.lock','a')
fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
results={}
for role in ['developer','reviewer']:
 r=registration('sampling',role)
 a,e=command(r,['/opt/loginom-swarm/runtime/bin/codex','login','status'])
 p=subprocess.run(a,env=e,capture_output=True,text=True,timeout=30)
 results[role]={'chatgptOAuth':p.returncode==0 and 'Logged in using ChatGPT' in p.stdout+p.stderr}
r=registration('sampling','acceptance')
a,e=command(r,['/usr/bin/xvfb-run','-a','/opt/loginom-worker/.local/share/loginom-ai-agent-cli/0.1.16-prod/bin/loginom-ai-agent-cli','--no-headless','loginom','check','--format','json'],network=True)
p=subprocess.run(a,env=e,capture_output=True,text=True,timeout=180)
records=[]
for line in p.stdout.splitlines():
 try:item=json.loads(line)
 except ValueError:continue
 if isinstance(item,dict):records.append({k:item[k] for k in ('state','hasApiKey','hasPassword','code','ok') if k in item})
results['acceptance']={'exitCode':p.returncode,'status':records,'strictRecovery':e.get('LOGINOM_AI_AGENT_STRICT_RECOVERY')=='1'}
print(json.dumps(results))
if not all(results[r]['chatgptOAuth'] for r in ['developer','reviewer']) or p.returncode:raise SystemExit(1)
