#!/bin/bash
# Operator-uploaded source; update only while the shared heavy lock is free.
set -euo pipefail
umask 077
test "$(id -u)" = 0
source_dir=$(cd "$(dirname "$0")/.." && pwd)
exec 8>/opt/loginom-worker/state/heavy.lock
flock -n 8 || { echo 'Active work or backup: update refused'; exit 75; }
root=/opt/loginom-swarm
stamp=$(date -u +%Y%m%dT%H%M%SZ)
rollback="$root/rollbacks/$stamp"
mkdir -p "$rollback"
cp -a "$root/runtime" "$rollback/runtime"
staging=$(mktemp -d "$root/.runtime-XXXXXX")
cp -a "$root/runtime/." "$staging/"
install -m 644 "$source_dir"/runtime/*.py "$staging/"
chmod 755 "$staging"
python3 -m compileall -q "$staging"
restore() {
 systemctl stop loginom-swarm-worker || true
 mv "$root/runtime" "$rollback/failed-runtime"
 cp -a "$rollback/runtime" "$root/runtime"
 systemctl start loginom-swarm-worker
}
systemctl stop loginom-swarm-worker
mv "$root/runtime" "$rollback/replaced-runtime"
mv "$staging" "$root/runtime"
trap restore ERR
systemctl start loginom-swarm-worker
for attempt in $(seq 1 50); do
 if curl -fsS --unix-socket /run/loginom-swarm/control.sock http://localhost/health > "$rollback/health.json"; then
  python3 - "$rollback/health.json" <<'PY'
import json,sys
r=json.load(open(sys.argv[1]));assert r['processingEnabled'] is False and r['executionProtocol']==1
PY
  trap - ERR
  echo "Worker protocol updated; rollback $rollback; node processing remains disabled."
  exit 0
 fi
 sleep .1
done
false
