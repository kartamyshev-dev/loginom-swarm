#!/bin/bash
# Persist the already qualified network policy. Never restart workloads.
set -euo pipefail
umask 077
[[ $EUID == 0 && $# == 1 ]] || { echo 'Usage: sudo install-network.sh EXPECTED_MACHINE_ID' >&2; exit 1; }
[[ $(cat /etc/machine-id) == "$1" ]] || { echo 'Wrong destination machine' >&2; exit 1; }
ip -4 addr show dev ens18 | grep -q 'inet 10.200.4.106/' || { echo 'Wrong destination address' >&2; exit 1; }
[[ -f /etc/loginom-swarm-vpn/config.json ]] || { echo 'VPN installation missing' >&2; exit 1; }
command -v netplan >/dev/null
[[ -f /run/systemd/network/10-netplan-ens18.network ]] || { echo 'Expected networkd interface configuration missing' >&2; exit 1; }
install -d -m 0755 /etc/systemd/resolved.conf.d /etc/systemd/network/10-netplan-ens18.network.d /etc/systemd/system/docker.service.d
# Preserve the first pre-install versions; repeated execution must not replace rollback evidence.
backup=/var/lib/loginom-swarm-migration/network-before
install -d -m 0700 "$backup"
for file in /etc/netplan/99-loginom-swarm.yaml /etc/systemd/resolved.conf.d/90-swarm-vpn.conf /etc/systemd/network/10-netplan-ens18.network.d/90-swarm-dns.conf /etc/systemd/system/docker.service.d/50-swarm-firewall.conf; do
 key=${file//\//_}
 if [[ ! -e "$backup/$key.present" && ! -e "$backup/$key.absent" ]]; then
  if [[ -e $file ]]; then cp -a "$file" "$backup/$key"; touch "$backup/$key.present"; else touch "$backup/$key.absent"; fi
 fi
done
cat > /etc/netplan/99-loginom-swarm.yaml <<'YAML'
network:
  version: 2
  ethernets:
    ens18:
      dhcp4: true
      dhcp4-overrides:
        send-hostname: true
        hostname: loginom-swarm
        use-hostname: false
        use-domains: route
        use-dns: false
      dhcp6-overrides:
        send-hostname: true
        hostname: loginom-swarm
        use-hostname: false
        use-domains: route
        use-dns: false
      nameservers:
        addresses: [10.200.0.3, 10.200.0.4]
        search: ["~bg.local", "~basegroup.ru"]
YAML
chmod 0600 /etc/netplan/99-loginom-swarm.yaml
cat > /etc/systemd/resolved.conf.d/90-swarm-vpn.conf <<'CONF'
[Resolve]
DNS=127.0.0.1:5353
FallbackDNS=
Domains=~.
DNSOverTLS=no
CONF
cat > /etc/systemd/network/10-netplan-ens18.network.d/90-swarm-dns.conf <<'CONF'
[Network]
DNSDefaultRoute=no
CONF
cat > /etc/systemd/system/docker.service.d/50-swarm-firewall.conf <<'CONF'
[Unit]
Requires=swarm-vpn-firewall.service
After=swarm-vpn-firewall.service
CONF
chmod 0644 /etc/systemd/resolved.conf.d/90-swarm-vpn.conf /etc/systemd/network/10-netplan-ens18.network.d/90-swarm-dns.conf /etc/systemd/system/docker.service.d/50-swarm-firewall.conf
netplan generate
systemctl daemon-reload
printf 'Persistent files installed and generated. No network reload or service restart performed.\n'
printf 'Apply only under the documented administrative rollback watchdog.\n'
