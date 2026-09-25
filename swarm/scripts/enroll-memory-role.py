#!/usr/bin/python3 -I
"""Enroll only a role with real, independently observed Codex bootstrap evidence."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time

assert os.geteuid() == 0
role = sys.argv[1]
assert role in {'developer', 'reviewer'}
lock = open('/opt/loginom-worker/state/heavy.lock', 'a')
fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
path = Path('/etc/loginom-swarm/memory-roles') / (role + '.json')
record = json.loads(path.read_text())
assert record['status'] == 'pending'
receipt_path = Path('/opt/loginom-worker/state') / ('memory-bootstrap-' + role + '.json')
receipt = json.loads(receipt_path.read_text())
profile = Path(record['profile'])
thread = receipt['threadId']
assert re.fullmatch(r'[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}', thread)
assert all(receipt[k] == record[k] for k in ['role', 'generation', 'cwd'])
assert receipt['model'] == 'gpt-6-astra' and receipt['effort'] == 'medium'
assert receipt['turnStatus'] == 'completed' and receipt['developmentStarted'] is False
assert 0 <= time.time() - receipt['checkedAt'] < 86400
observed = json.loads((profile / 'swarm-memory/bootstrap.json').read_text())
assert observed == receipt['observedSessionStart']
assert observed['threadId'] == thread and observed['observedEvent'] == 'SessionStart'
assert hashlib.sha256((profile / 'hooks.json').read_bytes()).hexdigest() == record['hooksSha256']
assert len(receipt['hooks']) == 5 and all(h['trustStatus'] == 'trusted' for h in receipt['hooks'])
completed = {e['run']['eventName'] for e in receipt['events']
             if e['method'] == 'hook/completed' and e['threadId'] == thread
             and e['run']['status'] == 'completed'
             and e['run']['sourcePath'] == str(profile / 'hooks.json')}
assert {'sessionStart', 'userPromptSubmit', 'stop'} <= completed
assert any(e['method'] == 'turn/completed' and e['threadId'] == thread
           and e['turn'] == {'id': receipt['turnId'], 'status': 'completed'} for e in receipt['events'])

# Seal reviewed definitions/config outside the writable profile. The sandbox
# overlays these files read-only, including the file's parent traversal checks.
sealed = Path('/etc/loginom-swarm/memory-sealed') / role
sealed.mkdir(parents=True, exist_ok=True)
sealed.parent.chmod(0o755)
sealed.chmod(0o755)
record['sealedFiles'] = {}
for name in ['hooks.json', 'config.toml']:
    source = profile / name
    assert source.is_file() and not source.is_symlink()
    target = sealed / name
    target.write_bytes(source.read_bytes())
    target.chmod(0o644)
    record['sealedFiles'][name] = {'path': str(target), 'sha256': hashlib.sha256(target.read_bytes()).hexdigest()}

config_path = Path('/etc/loginom-swarm/memory-gateway.json')
gateway = json.loads(config_path.read_text())
connection = json.loads((profile / '.openviking/ovcli.conf').read_text())
digest = hashlib.sha256(connection['api_key'].encode()).hexdigest()
principal = gateway['principals'][digest]
assert principal['role'] == role and principal['status'] == 'pending'
record.update(status='active', threadId=thread, bootstrapReceiptSha256=hashlib.sha256(receipt_path.read_bytes()).hexdigest())
principal.update(status='active', threadId=thread)
# Service reload happens only after both records have been written by operator.
path.write_text(json.dumps(record, indent=2) + '\n')
config_path.write_text(json.dumps(gateway) + '\n')
print(json.dumps({'role': role, 'threadId': thread, 'enrollment': 'active', 'memoryQualified': False}))
