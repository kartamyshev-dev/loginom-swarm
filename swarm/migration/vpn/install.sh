#!/bin/bash
# Installs artifacts only; activate after independent review and LAN SSH test.
set -euo pipefail
umask 077
[[ $EUID == 0 && $# == 4 ]] || { echo 'Usage: sudo install.sh EXPECTED_MACHINE_ID GENERATED_DIR SING_BOX_ARCHIVE OFFICIAL_SHA256' >&2; exit 1; }
[[ $(cat /etc/machine-id) == "$1" ]] || { echo 'Wrong destination machine' >&2; exit 1; }
ip -4 addr show dev ens18 | grep -q 'inet 10.200.4.106/' || { echo 'Wrong destination address' >&2; exit 1; }
[[ $(uname -m) == x86_64 ]] || exit 1
[[ $4 =~ ^[a-f0-9]{64}$ ]] || exit 1
actual=$(sha256sum "$3"); [[ ${actual%% *} == "$4" ]] || { echo 'Archive checksum mismatch' >&2; exit 1; }
for program in nft python3 docker systemctl; do command -v "$program" >/dev/null; done
[[ $(iptables --version) == *nf_tables* ]] || { echo 'Requires iptables-nft Docker backend' >&2; exit 1; }
if [[ -f /etc/docker/daemon.json ]]; then
 python3 -c 'import json; assert json.load(open("/etc/docker/daemon.json")).get("firewall-backend", "iptables") == "iptables"'
fi
[[ -d /sys/class/net/br-swarm ]] || { echo 'Create external Docker network swarm-lan / br-swarm 172.28.0.0/24 first' >&2; exit 1; }
[[ ! -e /etc/loginom-swarm-vpn ]] || { echo 'VPN already installed; reviewed update procedure required' >&2; exit 1; }
! getent passwd 21004 >/dev/null && ! getent group 21004 >/dev/null || { echo 'VPN UID/GID occupied' >&2; exit 1; }
script_dir=$(cd -- "$(dirname -- "$0")" && pwd)
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
tar -xzf "$3" --directory "$work" --no-same-owner
binary="$work/sing-box-1.12.25-linux-amd64/sing-box"
[[ -f $binary ]] && "$binary" version | grep -q '^sing-box version 1.12.25$'
"$binary" check -c "$2/config.json" >/dev/null 2>&1 || { echo 'sing-box config validation failed (secret output suppressed)' >&2; exit 1; }
nft -c -f "$2/firewall.nft"
groupadd -g 21004 swarm-vpn
useradd -u 21004 -g 21004 --system --home-dir /nonexistent --shell /usr/sbin/nologin swarm-vpn
install -d -m 0755 /usr/local/libexec/swarm-vpn
install -d -m 0750 -o root -g swarm-vpn /etc/loginom-swarm-vpn
install -m 0755 "$binary" /usr/local/libexec/swarm-vpn/sing-box
install -m 0640 -o root -g swarm-vpn "$2/config.json" /etc/loginom-swarm-vpn/config.json
install -m 0600 "$2/firewall.nft" /etc/loginom-swarm-vpn/firewall.nft
install -m 0755 "$script_dir/load-firewall" "$script_dir/check-egress" /usr/local/libexec/swarm-vpn/
install -m 0644 "$script_dir/swarm-vpn.service" "$script_dir/swarm-vpn-firewall.service" /etc/systemd/system/
systemctl daemon-reload
printf 'Installed only; no VPN, workload or firewall started. Follow activation checklist.\n'
