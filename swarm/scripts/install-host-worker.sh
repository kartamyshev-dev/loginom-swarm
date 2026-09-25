#!/bin/bash
# Run from an operator-uploaded checkout of swarm/, after toolchain verification.
set -euo pipefail
umask 077
test "$(id -u)" = 0
source_dir=$(cd -- "$(dirname -- "$0")/.." && pwd)
test -d /opt/loginom-swarm/toolchains/20260925.1
test ! -e /etc/systemd/system/loginom-swarm-worker.service || { echo 'Existing installation: use a reviewed update, not bootstrap.' >&2; exit 1; }
install -d -m 755 /opt/loginom-swarm/runtime /etc/loginom-swarm
install -m 644 "$source_dir"/runtime/*.py /opt/loginom-swarm/runtime/
install -m 644 "$source_dir/deploy/security/loginom-swarm-worker.apparmor" /etc/apparmor.d/loginom-swarm-worker
apparmor_parser -r /etc/apparmor.d/loginom-swarm-worker
# Dedicated infrastructure fixtures contain no source node implementation or auth.
python3 - <<'PY'
import json, os, pathlib, pwd
u=pwd.getpwnam('loginom-worker')
rows=[]
for role in ('developer','reviewer','acceptance'):
 row={'campaign':'infrastructure','role':role}
 for name, category in [('workspace','workspaces'),('profile','profiles')]:
  p=pathlib.Path('/opt/loginom-worker')/category/'infrastructure'/role
  p.mkdir(parents=True,mode=0o700,exist_ok=True)
  os.chown(p,u.pw_uid,u.pw_gid)
  # Parent must be traversable only by the worker/operator.
  os.chown(p.parent,u.pw_uid,u.pw_gid);p.parent.chmod(0o700)
  row[name]=str(p)
 rows.append(row)
p=pathlib.Path('/etc/loginom-swarm/roles.json')
if p.exists(): raise RuntimeError('Refusing to replace registration')
p.write_text(json.dumps(rows,indent=2)+'\n');p.chmod(0o644)
PY
install -m 644 "$source_dir/deploy/systemd/loginom-swarm-worker.service" /etc/systemd/system/loginom-swarm-worker.service
systemctl daemon-reload
systemctl enable --now loginom-swarm-worker.service
systemctl is-active loginom-swarm-worker.service
