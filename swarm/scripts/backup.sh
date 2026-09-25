#!/bin/bash
set -euo pipefail
umask 077
cd /opt/paperclip
exec 9>/run/lock/paperclip-backup.lock
flock -n 9 || exit 0
exec 8>/opt/loginom-worker/state/heavy.lock
flock -w 28800 8 || { echo 'Backup blocked: executor stage exceeded the 8-hour wait.'; exit 75; }
mkdir -p backups
stamp=$(date -u +%Y%m%dT%H%M%SZ)
backup_dir="backups/.partial-$stamp"
mkdir "$backup_dir"
worker_active=false
systemctl is-active --quiet loginom-swarm-worker && worker_active=true
restart_services() {
  docker compose start paperclip >/dev/null
  if "$worker_active"; then systemctl start loginom-swarm-worker; fi
}
trap restart_services EXIT
if "$worker_active"; then systemctl stop loginom-swarm-worker; fi
# Snapshot large worker files first while the board remains online. The shared
# lock excludes executor mutations. Compression runs after both services return.
tar --exclude='*/node_modules' --exclude='*/.cache' --exclude='*/.bun/install/cache' \
  --exclude='*/Cache' --exclude='*/Code Cache' --exclude='*/GPUCache' \
  --exclude='*/state/auth' --exclude='*/state/host-worker-bootstrap' \
  --exclude='*/state/sandbox-probe' --exclude='*.log' --exclude='*/state/heavy.lock' \
  -cf "$backup_dir/worker.tar" -C / \
  opt/loginom-worker/profiles opt/loginom-worker/workspaces opt/loginom-worker/repo \
  opt/loginom-worker/state opt/loginom-swarm/runtime etc/loginom-swarm \
  etc/apparmor.d/loginom-swarm-worker etc/systemd/system/loginom-swarm-worker.service
docker compose stop -t 60 paperclip
docker compose exec -T db pg_dump -U paperclip -d paperclip -Fc > "$backup_dir/database.dump"
/opt/paperclip/scripts/database-fingerprint.sh paperclip > "$backup_dir/database.rows.sha256"
tar -cf "$backup_dir/files.tar" .env compose.yaml Caddyfile scripts systemd data/paperclip
restart_services
trap - EXIT
gzip "$backup_dir/files.tar" "$backup_dir/worker.tar"
(cd "$backup_dir" && sha256sum database.dump database.rows.sha256 files.tar.gz worker.tar.gz > SHA256SUMS)
mv "$backup_dir" "backups/$stamp"
find backups -mindepth 1 -maxdepth 1 -type d -name '20*T*Z' -mmin +10080 -exec rm -rf -- {} +
echo "Backup completed: $stamp"
