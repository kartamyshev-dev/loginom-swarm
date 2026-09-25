#!/bin/bash
# One-shot database restore on the promoted LAN target. Never activates writers.
set -euo pipefail
umask 077
expected_machine=a52df24994be425abd799334b2aa5c86
[[ $EUID == 0 && $# == 1 && $1 == "$expected_machine" ]]
[[ $(cat /etc/machine-id) == "$expected_machine" ]]
state=/var/lib/loginom-migration
bundle=$state/incoming/20260925-lan
attempt=$state/db-restore-attempt
[[ -d $state && ! -L $state ]]
[[ ! -e $state/activation-approved && ! -e $state/db-restored.json ]]
[[ ! -e $attempt ]]
cd /opt/paperclip
exec 9>/run/lock/paperclip-backup.lock
flock -n 9
exec 8>/opt/loginom-worker/state/heavy.lock
flock -n 8
assert_frozen() {
  [[ ! -e $state/activation-approved ]]
  for unit in loginom-swarm-worker loginom-swarm-memory paperclip-backup.timer; do
    load=$(systemctl show "$unit" -p LoadState --value)
    [[ $load == loaded ]]
    status=$(systemctl show "$unit" -p ActiveState --value)
    [[ $status == inactive || $status == failed ]]
  done
  # Inspect all project containers, including a manually started application.
  ids=$(docker ps -q --filter label=com.docker.compose.project=paperclip)
  for id in $ids; do
    service=$(docker inspect --format '{{index .Config.Labels "com.docker.compose.service"}}' "$id")
    [[ $service == db ]]
  done
}
assert_frozen
# A prior DB container, even stopped, means this is no longer a first attempt.
[[ -z $(docker compose ps --all --quiet db) ]]
[[ ! -L data/postgres ]]
if [[ -e data/postgres ]]; then
  [[ -d data/postgres && -z $(find data/postgres -mindepth 1 -print -quit) ]]
fi

# These read-only checks must finish before creating the one-shot attempt marker.
python3 - "$state" <<'PY'
import hashlib, json, re, subprocess, sys
from pathlib import Path
root = Path(sys.argv[1])
receipt = json.loads((root/'promoted.json').read_text())
assert receipt == dict(filesInstalled=True, databaseRestored=False, servicesStarted=False)
bundle = root/'incoming/20260925-lan'
manifest = json.loads((bundle/'manifest.json').read_text())
assert manifest['complete'] is True and manifest['noRestart'] is True
assert manifest['machineId'] == 'a09aeb94b64a4975a65cba5c6f85b050'
for name in ('database.dump', 'database.roles.sql', 'database.rows.sha256'):
    path = bundle/name
    assert path.is_file() and not path.is_symlink()
    h = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024*1024), b''): h.update(block)
    assert h.hexdigest() == manifest['artifacts'][name], 'Database artifact hash mismatch'
assert re.fullmatch(r'[a-f0-9]{64}\n?', (bundle/'database.rows.sha256').read_text())
roles = (bundle/'database.roles.sql').read_text()
assert len(re.findall(r'^CREATE ROLE (?:paperclip|"paperclip");$', roles, re.M)) == 1
# Capture Compose output in memory: it includes application secrets.
config = json.loads(subprocess.run(['docker','compose','config','--format','json'],
                                  capture_output=True, check=True, text=True).stdout)
assert config['name'] == 'paperclip'
db = config['services']['db']
assert db['image'] == 'postgres@sha256:b0f9560a2de083e2cc7382e75f808c7381a32852a7ec49117deedb300e552b24'
assert not db.get('ports')
assert db['environment']['POSTGRES_USER'] == 'paperclip'
assert db['environment']['POSTGRES_DB'] == 'paperclip'
mounts = [m for m in db['volumes'] if m['target'] == '/var/lib/postgresql/data']
assert len(mounts) == 1 and mounts[0]['type'] == 'bind'
assert mounts[0]['source'] == '/opt/paperclip/data/postgres'
PY

# Atomic directory creation prevents retries even after a crash or power loss.
mkdir -m 0700 "$attempt"
finish() {
  code=$?
  trap - EXIT
  if [[ $code != 0 ]]; then
    docker compose stop -t 60 db >> "$attempt/restore.log" 2>&1 || true
    printf 'Restore failed; attempt retained. Reconcile before any retry.\n' >&2
  fi
  exit "$code"
}
trap finish EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
# No restore SQL or password hashes may reach the task transcript.
(
  set -euo pipefail
  python3 - "$bundle/database.roles.sql" "$attempt/roles.sql" <<'PY'
import re, sys
from pathlib import Path
text = Path(sys.argv[1]).read_text()
# initdb already creates precisely this owner. Preserve every ALTER ROLE and
# all other role statements; do not suppress SQL errors or use blanket filtering.
text, count = re.subn(r'^CREATE ROLE (?:paperclip|"paperclip");\n?', '', text, flags=re.M)
assert count == 1
Path(sys.argv[2]).write_text(text)
Path(sys.argv[2]).chmod(0o600)
PY
  docker compose up -d --no-deps --pull never db
  ready=false
  for ((i=0; i<90; i++)); do
    if docker compose exec -T db pg_isready -U paperclip -d paperclip; then
      ready=true
      break
    fi
    sleep 2
  done
  "$ready"
  version=$(docker compose exec -T db psql -XAt -U paperclip -d paperclip -v ON_ERROR_STOP=1 -c 'SHOW server_version_num')
  [[ $version =~ ^[0-9]+$ && $version -ge 170000 && $version -lt 180000 ]]
  tables=$(docker compose exec -T db psql -XAt -U paperclip -d paperclip -v ON_ERROR_STOP=1 -c "SELECT count(*) FROM pg_tables WHERE schemaname NOT IN ('pg_catalog','information_schema')")
  [[ $tables == 0 ]]
  docker compose exec -T db psql -X -U paperclip -d paperclip \
    -v ON_ERROR_STOP=1 --single-transaction < "$attempt/roles.sql"
  docker compose exec -T db pg_restore -U paperclip -d paperclip \
    --exit-on-error --single-transaction < "$bundle/database.dump"
  /opt/paperclip/scripts/database-fingerprint.sh paperclip > "$attempt/database.rows.sha256"
  cmp -s "$bundle/database.rows.sha256" "$attempt/database.rows.sha256"
  assert_frozen
  python3 - "$state" <<'PY'
import datetime, json, os, sys
from pathlib import Path
root = Path(sys.argv[1])
manifest = json.loads((root/'incoming/20260925-lan/manifest.json').read_text())
receipt = dict(databaseRestored=True, fingerprintMatched=True,
               applicationServicesStarted=False, databaseRunning=True,
               targetMachineId=Path('/etc/machine-id').read_text().strip(),
               databaseDumpSha256=manifest['artifacts']['database.dump'],
               completedAt=datetime.datetime.now(datetime.timezone.utc).isoformat())
path = root/'db-restore-attempt/db-restored.json'
with path.open('x') as output:
    json.dump(receipt, output, indent=2)
    output.write('\n')
    output.flush()
    os.fsync(output.fileno())
path.chmod(0o600)
# Link creates the final receipt atomically and refuses an existing destination.
os.link(path, root/'db-restored.json')
PY
) > "$attempt/restore.log" 2>&1
printf 'Database restored and fingerprint matched. Application and workers remain gated.\n'
