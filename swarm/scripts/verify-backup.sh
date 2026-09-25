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
# Compare canonical table contents with the current idle instance; run this check
# immediately after a backup and before users begin changing application data.
for database in paperclip "$test_db"; do
  docker compose exec -T db psql -X -A -t -U paperclip -d "$database" -v ON_ERROR_STOP=1 > "$work_dir/$database.sql" <<'SQL'
SELECT format('SELECT %L, COALESCE(jsonb_agg(to_jsonb(t) ORDER BY to_jsonb(t)::text), %L::jsonb) FROM %I.%I t;', schemaname || '.' || tablename, '[]', schemaname, tablename)
FROM pg_tables WHERE schemaname NOT IN ('pg_catalog', 'information_schema') ORDER BY schemaname, tablename
\gexec
SQL
done
cmp -s "$work_dir/paperclip.sql" "$work_dir/$test_db.sql"
echo 'Restored database data matches the live idle database.'
tar -xzf "$backup_dir/files.tar.gz" -C "$work_dir" ./data/paperclip/instances/default/config.json 2>/dev/null ||
  tar -xzf "$backup_dir/files.tar.gz" -C "$work_dir" data/paperclip/instances/default/config.json
cmp -s data/paperclip/instances/default/config.json "$work_dir/data/paperclip/instances/default/config.json"
echo 'Restored persistent configuration matches the live file.'
if [ -f "$backup_dir/worker.tar.gz" ]; then
  mkdir "$work_dir/worker"
  tar -xzf "$backup_dir/worker.tar.gz" -C "$work_dir/worker"
  python3 - "$work_dir/worker" <<'PYWORKER'
import json, pathlib, stat, sys
root=pathlib.Path(sys.argv[1])
rows=json.loads((root/'etc/loginom-swarm/roles.json').read_text())
assert rows
for row in rows:
 for key in ['workspace','profile']:
  assert (root/row[key].lstrip('/')).is_dir()
for p in (root/'opt/loginom-worker/profiles').rglob('auth.json'):
 assert p.stat().st_mode & 0o077 == 0
assert (root/'etc/systemd/system/loginom-swarm-worker.service').is_file()
print('Worker archive extracted separately; registrations, directories and auth permissions verified.')
PYWORKER
fi
