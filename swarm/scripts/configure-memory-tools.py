#!/usr/bin/python3 -I
"""Operator-only addition of the scoped MCP tools to a sealed role config."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import tomllib

assert os.geteuid()==0
lock=open('/opt/loginom-worker/state/heavy.lock','a')
fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
for role in ['developer','reviewer']:
    path=Path('/etc/loginom-swarm/memory-roles')/(role+'.json')
    record=json.loads(path.read_text())
    config=Path(record['sealedFiles']['config.toml']['path'])
    before=config.read_text()
    parsed=tomllib.loads(before)
    if 'swarm_openviking' in parsed.get('mcp_servers',{}):raise RuntimeError('Already configured; inspect existing definition')
    after=before+f'''
[mcp_servers.swarm_openviking]
command = "/usr/bin/python3"
args = ["-I", "/opt/loginom-swarm/memory/mcp.py", "{role}"]
startup_timeout_sec = 20
tool_timeout_sec = 60
'''
    tomllib.loads(after)
    config.write_text(after)
    record['sealedFiles']['config.toml']['sha256']=hashlib.sha256(config.read_bytes()).hexdigest()
    path.write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps({'memoryToolsConfigured':['developer','reviewer'],'nodeStarted':False}))
