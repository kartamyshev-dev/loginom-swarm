#!/bin/bash
set -euo pipefail
umask 077
cd /opt/paperclip
backup_dir=${1:?Usage: verify-backup.sh /opt/paperclip/backups/TIMESTAMP}
(cd "$backup_dir" && sha256sum -c SHA256SUMS)
tar -tzf "$backup_dir/files.tar.gz" >/dev/null
test_db="paperclip_restore_check_$(date +%s)_$$"
# Full runtime archives can exceed a RAM-backed /tmp on the LAN host.
work_dir=$(mktemp -d /opt/paperclip/backups/.verify-XXXXXXXX)
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
if [ ! -f "$backup_dir/snapshot-manifest.json" ]; then
  echo 'Legacy backup: no self-contained file manifest; file restoration not verified.' >&2
  exit 1
fi
for archive in files worker secrets; do
  mkdir "$work_dir/$archive"
  tar --acls --xattrs --xattrs-include='*' --numeric-owner --same-owner \
    -xzf "$backup_dir/$archive.tar.gz" -C "$work_dir/$archive"
done
/opt/paperclip/scripts/backup-manifest.py verify "$backup_dir" "$work_dir"
echo 'Database and archived files verified against their snapshot; live profiles were not read.'
