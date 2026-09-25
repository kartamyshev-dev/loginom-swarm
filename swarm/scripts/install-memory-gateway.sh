#!/bin/bash
# Run as root with a reviewed source checkout and root-provisioned configuration.
set -euo pipefail
umask 077
source_dir=$(cd "$(dirname "$0")/.." && pwd)
test "$(id -u)" = 0
id loginom-memory >/dev/null 2>&1 || useradd --system --user-group --home-dir /var/lib/loginom-swarm-memory --shell /usr/sbin/nologin loginom-memory
install -d -m 755 /opt/loginom-swarm/memory
install -m 644 "$source_dir"/memory/{gateway,gateway_policy,serve}.py /opt/loginom-swarm/memory/
install -m 644 "$source_dir"/memory/{mcp.py,hook.mjs} /opt/loginom-swarm/memory/
cp -R "$source_dir/memory/vendor-plugin" /opt/loginom-swarm/memory/
find /opt/loginom-swarm/memory/vendor-plugin -type d -exec chmod 755 {} +
find /opt/loginom-swarm/memory/vendor-plugin -type f -exec chmod 644 {} +
chown root:loginom-memory /etc/loginom-swarm/memory-gateway.json
chmod 640 /etc/loginom-swarm/memory-gateway.json
install -m 644 "$source_dir/deploy/systemd/loginom-swarm-memory.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now loginom-swarm-memory
