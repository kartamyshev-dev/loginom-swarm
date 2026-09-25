#!/bin/bash
set -euo pipefail
umask 077
cd /opt/paperclip
exec 9>/run/lock/paperclip-backup.lock
flock -n 9 || exit 75
exec 8>/opt/loginom-worker/state/heavy.lock
flock -w 28800 8 || { echo 'Backup blocked: executor stage exceeded the 8-hour wait.'; exit 75; }
mkdir -p backups
stamp=$(date -u +%Y%m%dT%H%M%SZ)
backup_dir="backups/.partial-$stamp"
mkdir "$backup_dir"

# This daily backup belongs to the LAN target. Source service IDs collide with
# container identities (publisher 999 / PostgreSQL 999); never deploy it there.
for mapping in loginom-worker:21001 loginom-publisher:21002 loginom-memory:21003; do
  account=${mapping%:*}
  expected=${mapping#*:}
  actual=$(id -u "$account")
  [ "$actual" = "$expected" ] || {
    echo 'Backup blocked: expected dedicated LAN service UIDs 21001/21002/21003.'; exit 75;
  }
done

# Read all initial states successfully before stopping anything. Errors querying
# Docker/systemd are not evidence that a service was previously stopped.
active_units=()
for unit in loginom-swarm-worker loginom-swarm-memory loginom-swarm-publisher; do
  loaded=$(systemctl show "$unit" -p LoadState --value)
  if [ "$loaded" = not-found ]; then continue; fi
  [ "$loaded" = loaded ] || { echo 'Backup blocked: unresolved systemd unit.'; exit 75; }
  state=$(systemctl show "$unit" -p ActiveState --value)
  case "$state" in
    active) active_units+=("$unit");;
    inactive|failed) ;;
    *) echo 'Backup blocked: service is changing state.'; exit 75;;
  esac
done
active_containers=()
for service in paperclip caddy db; do
  ids=$(docker compose ps --all --quiet "$service")
  [ -n "$ids" ] && [[ "$ids" != *$'\n'* ]] || {
    echo 'Backup blocked: expected exactly one container per service.'; exit 75;
  }
  state=$(docker inspect --format '{{.State.Status}}' "$ids")
  case "$state" in
    running) [ "$service" = db ] || active_containers+=("$service");;
    exited|created) [ "$service" != db ] || { echo 'Backup blocked: database is not running.'; exit 75; };;
    *) echo 'Backup blocked: container is changing state.'; exit 75;;
  esac
done
printf '%s\n' "${active_units[@]}" > "$backup_dir/active-units.txt"
printf '%s\n' "${active_containers[@]}" > "$backup_dir/active-containers.txt"

restore_needed=false
restore_services() {
  local failed=0
  if "$restore_needed"; then
    # Only identities proven active before the snapshot may be restarted.
    if [ ${#active_containers[@]} -gt 0 ]; then
      docker compose start "${active_containers[@]}" >/dev/null || failed=1
    fi
    for unit in "${active_units[@]}"; do
      systemctl start "$unit" || failed=1
    done
    if [ "$failed" -eq 0 ]; then restore_needed=false; fi
  fi
  return "$failed"
}
finish() {
  local status=$?
  trap - EXIT
  if ! restore_services; then
    echo 'Backup failed to restore the previous service state.' >&2
    status=1
  fi
  exit "$status"
}
trap finish EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
restore_needed=true
# Stop the board before every file snapshot, not only before the database dump.
if [ ${#active_containers[@]} -gt 0 ]; then
  docker compose stop -t 60 "${active_containers[@]}" >/dev/null
fi
for unit in "${active_units[@]}"; do systemctl stop "$unit"; done
# Standalone publisher/role processes must finish; do not kill or ignore them.
for account in loginom-worker loginom-publisher loginom-memory; do
  if uid=$(id -u "$account" 2>/dev/null); then
    if pgrep -u "$uid" >/dev/null; then
      echo 'Backup blocked: a service account still has running processes.'; exit 75
    else
      rc=$?
      [ "$rc" -eq 1 ] || exit "$rc"
    fi
  fi
done

docker compose exec -T db pg_dump -U paperclip -d paperclip -Fc > "$backup_dir/database.dump"
# Role password hashes are secret and inherit umask 077.
docker compose exec -T db pg_dumpall -U paperclip --roles-only > "$backup_dir/database.roles.sql"
/opt/paperclip/scripts/database-fingerprint.sh paperclip > "$backup_dir/database.rows.sha256"
[ -s "$backup_dir/database.dump" ] && [ -s "$backup_dir/database.roles.sql" ]
grep -Eq '^[0-9a-f]{64}$' "$backup_dir/database.rows.sha256"

# Explicit roots avoid recursively including /opt/paperclip/backups. Keep runtime
# dependencies, installed CLI, profiles, recovery, logs and trusted hook evidence.
worker_paths=(opt/loginom-worker opt/loginom-swarm etc/loginom-swarm
  var/lib/loginom-swarm-publisher var/lib/loginom-swarm-memory)
shopt -s nullglob
for path in /etc/systemd/system/loginom-swarm* /etc/systemd/system/paperclip* \
  /etc/systemd/system/swarm-vpn* \
  /etc/apparmor.d/loginom-swarm* /etc/apparmor.d/local/loginom-swarm* \
  /etc/sysctl.d/*swarm* /etc/modules-load.d/*swarm*; do
  worker_paths+=("${path#/}")
done
tar --acls --xattrs --xattrs-include='*' --numeric-owner \
  --exclude='opt/loginom-worker/state/heavy.lock' \
  -cf "$backup_dir/worker.tar" -C / "${worker_paths[@]}"
file_paths=(.env compose.yaml Caddyfile scripts systemd data/paperclip)
for path in compose.override.yaml data/caddy data/caddy-config; do
  if [ -e "$path" ]; then file_paths+=("$path"); fi
done
tar --acls --xattrs --xattrs-include='*' --numeric-owner -cf "$backup_dir/files.tar" "${file_paths[@]}"
secret_paths=(etc/passwd etc/group)
for path in etc/loginom-swarm-vpn etc/ssh root/.ssh root/.config/loginom-swarm \
  root/.config/sing-box etc/netplan etc/systemd/resolved.conf.d \
  etc/docker/daemon.json etc/dnsmasq.d etc/nftables.conf \
  usr/local/libexec/swarm-vpn usr/local/libexec/loginom-swarm etc/systemd/network/10-netplan-ens18.network.d \
  etc/systemd/system/docker.service.d; do
  if [ -e "/$path" ]; then secret_paths+=("$path"); fi
done
tar --acls --xattrs --xattrs-include='*' --numeric-owner -cf "$backup_dir/secrets.tar" -C / "${secret_paths[@]}"
# Inventory is restoration guidance, not permission to replace system accounts.
docker compose images --format json > "$backup_dir/images.json"
dpkg-query -W -f='${Package}\t${Version}\n' > "$backup_dir/packages.tsv"

# Compression reads immutable archives after normal service availability returns.
restore_services
trap - EXIT INT TERM
/opt/paperclip/scripts/backup-manifest.py create "$backup_dir"
gzip "$backup_dir/files.tar" "$backup_dir/worker.tar" "$backup_dir/secrets.tar"
(cd "$backup_dir" && sha256sum database.dump database.roles.sql database.rows.sha256 \
  files.tar.gz worker.tar.gz secrets.tar.gz active-units.txt active-containers.txt \
  images.json packages.tsv snapshot-manifest.json > SHA256SUMS)
chmod 600 "$backup_dir"/*
mv "$backup_dir" "backups/$stamp"
find backups -mindepth 1 -maxdepth 1 -type d -name '20*T*Z' -mmin +10080 -exec rm -rf -- {} +
echo "Backup completed: $stamp"
