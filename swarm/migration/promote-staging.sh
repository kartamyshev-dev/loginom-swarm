#!/bin/bash
# Install verified files only. Database restore and service activation are separate.
set -euo pipefail
umask 077
[[ $EUID == 0 && $# == 1 && $(cat /etc/machine-id) == "$1" ]] || exit 1
[[ $1 == a52df24994be425abd799334b2aa5c86 ]] || exit 1
state=/var/lib/loginom-migration
[[ $(systemctl show loginom-migration-verify -p ActiveState --value) == inactive ]]
[[ $(systemctl show loginom-migration-verify -p Result --value) == success ]]
[[ $(systemctl show loginom-migration-verify -p ExecMainStatus --value) == 0 ]]
[[ ! -e $state/promoted.json ]]
[[ -z $(docker ps -aq --filter label=com.docker.compose.project=paperclip) ]]
for unit in loginom-swarm-worker loginom-swarm-memory; do
  if systemctl is-active --quiet "$unit"; then exit 1; fi
done
python3 - <<'PY'
import json
from pathlib import Path
root = Path('/var/lib/loginom-migration')
receipt = json.loads((root/'verify.log').read_text().splitlines()[-1])
assert receipt['verified'] is True and receipt['extracted'] is True
manifest = json.loads((root/'incoming/20260925-lan/manifest.json').read_text())
assert manifest['machineId'] == 'a09aeb94b64a4975a65cba5c6f85b050'
assert manifest['complete'] is True and receipt['files'] == len(manifest['files'])
# A generic extracted receipt does not prove the requested UID/GID remap.
for row in manifest['files']:
    st = (root/'restored'/row['path']).lstat()
    uid, gid = row['uid'], row['gid']
    if not row['path'].startswith('opt/paperclip/'):
        uid = {1000:21001, 999:21002, 997:21003}.get(uid, uid)
        gid = {1000:21001, 987:21002, 986:21003}.get(gid, gid)
    assert (st.st_uid, st.st_gid) == (uid, gid), 'Staged owner remap mismatch'

PY
stage=$state/restored
for path in opt/paperclip opt/loginom-worker opt/loginom-swarm etc/loginom-swarm \
  var/lib/loginom-swarm-memory var/lib/loginom-swarm-publisher \
  etc/systemd/system etc/apparmor.d; do
  [[ -d $stage/$path ]]
  mkdir -p "/$path"
  # Synthetic archive parents must not replace OS directory permissions.
  if [[ $path == etc/systemd/system || $path == etc/apparmor.d ]]; then
    metadata=$(stat -c '%u:%g:%a' "/$path")
  else
    metadata=
  fi
  rsync -aHAX --numeric-ids "$stage/$path/" "/$path/"
  if [[ -n $metadata ]]; then
    IFS=: read -r owner group mode <<< "$metadata"
    chown "$owner:$group" "/$path"
    chmod "$mode" "/$path"
  fi
done
install -m 0644 "$state/deployment/compose.lan.yaml" /opt/paperclip/compose.override.yaml
install -m 0644 "$state/deployment/Caddyfile" /opt/paperclip/Caddyfile
for role in worker memory; do
  install -d -m 0755 "/etc/systemd/system/loginom-swarm-$role.service.d"
  install -m 0644 "$state/deployment/$role-lan.conf" "/etc/systemd/system/loginom-swarm-$role.service.d/50-lan.conf"
done
for name in backup.sh backup-manifest.py verify-backup.sh; do
  install -m 0755 "$state/deployment/$name" "/opt/paperclip/scripts/$name"
done
install -d -m 0755 /opt/loginom-swarm/migration
install -m 0444 "$state/deployment/qualify-restored-runtime.py" /opt/loginom-swarm/migration/
python3 - <<'PY'
import json
from pathlib import Path
env=Path('/opt/paperclip/.env')
values={'PAPERCLIP_DOMAIN':'loginom-swarm.bg.local',
        'PAPERCLIP_BASE_URL':'http://loginom-swarm.bg.local'}
lines=[]
for line in env.read_text().splitlines():
    key=line.partition('=')[0].strip()
    if key in values: continue
    lines.append(line)
lines.extend(k+'='+v for k,v in values.items())
env.write_text('\n'.join(lines)+'\n'); env.chmod(0o600)
path=Path('/opt/paperclip/data/paperclip/instances/default/config.json')
cfg=json.loads(path.read_text())
cfg['server'].update(deploymentMode='authenticated', exposure='private',
                     allowedHostnames=['loginom-swarm.bg.local'])
cfg['auth'].update(baseUrlMode='explicit', publicBaseUrl='http://loginom-swarm.bg.local')
path.write_text(json.dumps(cfg,indent=2)+'\n')
PY
# Reboot must not activate restored writers before DB restore and qualification.
[[ ! -e $state/activation-approved ]]
for unit in loginom-swarm-worker.service loginom-swarm-memory.service paperclip-backup.service paperclip-backup.timer; do
  install -d -m 0755 "/etc/systemd/system/$unit.d"
  printf '[Unit]\nConditionPathExists=/var/lib/loginom-migration/activation-approved\n' > "/etc/systemd/system/$unit.d/99-migration-gate.conf"
  chmod 0644 "/etc/systemd/system/$unit.d/99-migration-gate.conf"
done
apparmor_parser -r /etc/apparmor.d/loginom-swarm-worker
systemctl daemon-reload
cd /opt/paperclip
docker compose config --quiet
printf '{"filesInstalled":true,"databaseRestored":false,"servicesStarted":false}\n' > "$state/promoted.json"
chmod 600 "$state/promoted.json"
echo 'Verified files installed; database restore and activation remain pending.'
