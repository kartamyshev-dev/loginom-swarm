#!/bin/bash
set -euo pipefail
umask 077
cd /opt/paperclip
backup_dir=${1:?Usage: verify-backup.sh /opt/paperclip/backups/TIMESTAMP}
(cd "$backup_dir" && sha256sum -c SHA256SUMS)
tar -tzf "$backup_dir/files.tar.gz" >/dev/null
test_db="paperclip_restore_check_$(date +%s)_$$"
work_dir=$(mktemp -d)
created=false
cleanup() {
  if "$created"; then docker compose exec -T db dropdb -U paperclip "$test_db"; fi
  rm -rf -- "$work_dir"
}
trap cleanup EXIT
docker compose exec -T db createdb -U paperclip "$test_db"
created=true
docker compose exec -T db pg_restore -U paperclip -d "$test_db" --exit-on-error < "$backup_dir/database.dump"
docker compose exec -T db psql -X -U paperclip -d "$test_db" -v ON_ERROR_STOP=1 -c "SELECT count(*) AS restored_public_tables FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE'; SELECT count(*) AS restored_invites FROM invites;"
# Compare to the snapshot taken while Paperclip was stopped, not the restarted
# production database (which has legitimate heartbeat/audit changes).
if [ -f "$backup_dir/database.rows.sha256" ]; then
  /opt/paperclip/scripts/database-fingerprint.sh "$test_db" > "$work_dir/restored.rows.sha256"
  cmp -s "$backup_dir/database.rows.sha256" "$work_dir/restored.rows.sha256"
  echo 'Restored database rows match the backup snapshot fingerprint.'
else
  echo 'Legacy backup restored; snapshot row fingerprint is not available.'
fi
tar -xzf "$backup_dir/files.tar.gz" -C "$work_dir" ./data/paperclip/instances/default/config.json 2>/dev/null ||
  tar -xzf "$backup_dir/files.tar.gz" -C "$work_dir" data/paperclip/instances/default/config.json
cmp -s data/paperclip/instances/default/config.json "$work_dir/data/paperclip/instances/default/config.json"
echo 'Restored persistent configuration matches the live file.'
if [ -f "$backup_dir/worker.tar.gz" ]; then
  mkdir "$work_dir/worker"
  tar -xzf "$backup_dir/worker.tar.gz" -C "$work_dir/worker"
  python3 - "$work_dir/worker" <<'PYWORKER'
import hashlib, json, pathlib, stat, sys
root=pathlib.Path(sys.argv[1])
rows=json.loads((root/'etc/loginom-swarm/roles.json').read_text())
assert rows
for row in rows:
 for key in ['workspace','profile']:
  assert (root/row[key].lstrip('/')).is_dir()
for p in (root/'opt/loginom-worker/profiles').rglob('auth.json'):
 assert p.stat().st_mode & 0o077 == 0
assert (root/'etc/systemd/system/loginom-swarm-worker.service').is_file()
publisher=root/'var/lib/loginom-swarm-publisher'
if publisher.exists():
 credential=publisher/'.config/gh/hosts.yml'
 assert credential.is_file() and credential.stat().st_mode & 0o077 == 0
 assert publisher.stat().st_mode & 0o077 == 0
 assert credential.read_bytes() == pathlib.Path('/var/lib/loginom-swarm-publisher/.config/gh/hosts.yml').read_bytes()
 print('Publisher OAuth profile restored separately; bytes and private modes match.')
memory=root/'etc/loginom-swarm/memory-gateway.json'
if (root/'opt/loginom-swarm/memory').exists():
 assert memory.is_file() and memory.stat().st_mode & 0o027 == 0
 assert (root/'var/lib/loginom-swarm-memory').is_dir()
 assert (root/'etc/systemd/system/loginom-swarm-memory.service').is_file()
 gateway=json.loads(memory.read_text())
 for p in (root/'etc/loginom-swarm/memory-roles').glob('*.json'):
  role=json.loads(p.read_text())
  if role['status']!='active':continue
  assert any(v['threadId']==role['threadId'] and v['role']==role['role'] for v in gateway['principals'].values())
  profile=root/role['profile'].lstrip('/')
  cursor=json.loads((profile/'swarm-memory'/(role['threadId']+'.json')).read_text())
  assert cursor['codexSessionId']==role['threadId'] and cursor['workspacePeerId']==role['peer']
  for entry in role['sealedFiles'].values():
   file=root/entry['path'].lstrip('/')
   assert hashlib.sha256(file.read_bytes()).hexdigest()==entry['sha256']
   assert file.stat().st_mode & 0o022 == 0
 print('Memory gateway, enrolled threads, capture cursors and sealed configuration restored consistently.')
print('Worker archive extracted separately; registrations, directories and auth permissions verified.')
PYWORKER
fi
