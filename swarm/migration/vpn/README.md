# Mandatory VPN migration artifacts

The current subscription selects Trojan WebSocket TLS (verified certificates),
with path/Host/SNI taken from the protected URI. The old VLESS REALITY TCP parser
is retained only for compatibility; do not deploy the obsolete supplied VLESS
profile. Hysteria2 and VLESS XHTTP are intentionally unsupported here.

Local tests are not live qualification. Nothing here starts a model or unlocks
Sampling. The migration operator applies these artifacts sequentially.

## Inputs and installation

Require x86_64 Ubuntu, iptables-nft Docker backend, nftables, Python 3, curl,
working TUN and CAP_NET_ADMIN. Install sing-box **1.12.25** from its official
linux-amd64 release archive; obtain and review SHA256 from the official release
checksums independently. The installer checks the archive hash and binary version,
never downloads a floating release. Do not pass a subscription URI on a command line.

1. Store the selected subscription URI in a root-owned 0600 file outside Git. Resolve the
   VPN endpoint before filtering, compare with intended host, and pass its IPv4
   address explicitly. Expected exit `185.21.15.251` is NOT endpoint address.
2. Verify route/subnet non-overlap. Reserve `172.30.255.0/30` for TUN and
   `172.28.0.0/24` for Docker. Create persistent external network:
   `docker network create --driver bridge --subnet 172.28.0.0/24 --gateway 172.28.0.1 --opt com.docker.network.bridge.name=br-swarm swarm-lan`.
   Compose must use this network; do not let Compose destroy it.
3. `python3 generate.py --uri-file /protected/vless-uri --endpoint-ip ENDPOINT --output /protected/vpn-generated`
4. `sudo ./install.sh EXPECTED_MACHINE_ID /protected/vpn-generated /protected/sing-box-1.12.25-linux-amd64.tar.gz OFFICIAL_SHA256`
   This checks exact destination address `10.200.4.106` and machine ID, refuses
   existing installation/UID collisions, and installs only. Do not reuse this
   initial installer to update existing deployments. Protected files are not logged.

Host TCP auto_redirect may rewrite destination to 127.0.0.1 before route
relookup while the OUTPUT interface still reads ens18. Its narrow exception
requires loopback destination, TCP, DNAT and original public destination; it does
not require oif lo and does not permit direct public traffic.

Only the dedicated sing-box UID21004 may connect directly to pinned endpoint443.
Service receives network administration capabilities, no shared root credentials.
The firewall independently blocks direct public IPv4/IPv6 even with dead TUN.
Host UDP/ICMP marked 0x2023 by sing-box may still show the physical interface
before route relookup, so OUTPUT narrowly permits that IPv4 mark/protocol pair.
This is NOT permission for physical egress: a separate filter POSTROUTING chain
at priority110 (after source NAT) checks the actual final interface/destination
with default DROP. It contains no mark or established-flow bypass. Only loopback,
IPv4 TUN, explicit LAN/bridge, DHCP and dedicated UID endpoint443 are allowed.
Marked public UDP/ICMP still pointing at ens18 is dropped there; forged marks
cannot provide direct egress. Both chains must always be installed atomically.
LAN HTTP80 replies after Docker source NAT remain allowed by destination LAN;
local TCP DNAT remains allowed after relookup through loopback. Include NTP/UDP
and missing-policy-route tests in live failure qualification.
Docker remains on iptables-nft; our independent inet table runs at priority10.
Never flush the whole ruleset. Loading replaces only our table atomically.

## Controlled activation

Keep workers, memory, Paperclip and all copied OAuth profiles stopped. Have a
second LAN SSH session open. Confirm the operator IP belongs to 10.200/16 or
10.150/22; otherwise extend explicit administration ranges in reviewed files
before loading. Save current network, resolver and firewall state root-only.

Before applying changes schedule a five-minute systemd-run transient rollback
that **stops/masks workloads first**, stops sing-box, restores prior resolver
configuration and removes only `inet swarm_vpn`. This administrative recovery
must never restart Docker or model services. Cancel timer only after independent
SSH, DNS and egress tests pass. Do not install a persistent automatic rollback
that would remove the production kill switch after an ordinary VPN failure.

Start/enable `swarm-vpn-firewall.service` first, then `swarm-vpn.service`.
No ExecStop removes the firewall. Initial service startup needs existing br-swarm.
Validate with `sing-box check` (installer does this with output suppressed).
Use systemd-resolved, preserving /etc/resolv.conf symlink:
configure global DNS `127.0.0.1:5353`, Domains `~.`, empty FallbackDNS;
set the ens18 per-link routing domains to `~bg.local ~basegroup.ru`, DNS to
10.200.0.3 and 10.200.0.4, DNSDefaultRoute=no, and disable DHCP public DNS
adoption. This keeps corporate resolver access during VPN failure. Persist via
the actual Netplan renderer, do not mix independent generated network files.
Docker service containers use DNS `172.28.0.1`, not host loopback; their embedded
127.0.0.11 DNS still handles service names. DNS port53 listens only on bridge IP.

The generated config currently uses corporate DNS10.200.0.3 inside sing-box;
systemd-resolved has both internal resolvers. Public DNS always uses proxy DoT.
SNI preserved, endpoint IPv4 pinned; changing endpoint requires explicit review,
config/firewall atomic update and new egress qualification.

Add Requires/After for firewall+VPN to worker/memory systemd drop-ins and run
`check-egress` in ExecStartPre. Docker daemon must require/after firewall; avoid
Docker->VPN dependency cycle because VPN DNS binds the persistent Docker bridge.
Paperclip Compose startup must require VPN+egress via its own systemd wrapper.
Run egress check again before every provider stage: startup ordering alone is
not a readiness guarantee. Do not call localhost DNS inside isolated namespaces
unless the namespace actually shares host networking.

## Qualification (operator must record evidence)

Run `check-egress` on host, real worker sandbox, each relevant container and
Chromium (two external HTTPS IP services; must both equal 185.21.15.251). Check
DNS public and corporate separately. Record only sanitized status/counters.
Test stop, SIGKILL, endpoint-unreachable, reboot and Docker restart. During each
fault check no public IPv4/IPv6 or DNS packets escape ens18 except VPN endpoint;
provider attempts must fail, LAN SSH/HTTP must remain available. Packet counters
and packet capture are required: a failed curl alone does not prove no leak.
Restore VPN; no campaign/model resume occurs automatically after unknown mutation.

In sing-tun v0.7.13, TCP REDIRECT returns before the non-TCP mark rule;
Docker TCP therefore MUST NOT require mark 0x2023. The INPUT exception requires
br-swarm source/interface, bridge destination 172.28.0.1, TCP, conntrack DNAT
status, and an original IPv4 destination outside the explicit nonpublic set.
Direct access to the listener (no DNAT) and redirects of private destinations
remain denied. sing-box 1.12.25 does not expose a deterministic redirect port
in TunInboundOptions; do not hardcode an ephemeral port from a prior startup.
Only trusted root/CAP_NET_ADMIN services may create NAT rules; workers lack that
capability. Verify the actual redirected destination and conntrack tuple live.
Never replace this exception with unrestricted INPUT accept. Verify unrelated interfaces cannot reach proxy or
DNS listeners. Check LAN published HTTP80 and no public ingress path. Preserve
AppArmor and normal Bubblewrap/Chromium sandbox throughout.

Local validation: `python3 swarm/migration/vpn/test_vpn.py`; `bash -n install.sh`.
References: pinned [TUN docs](https://raw.githubusercontent.com/SagerNet/sing-box/v1.12.25/docs/configuration/inbound/tun.md),
[Docker firewall docs](https://docs.docker.com/engine/network/packet-filtering-firewalls/).
The previous deploy-vpn scripts were read for context only; no files there changed.

## Persistent network configuration

`sudo ./install-network.sh EXPECTED_MACHINE_ID` records the selected persistent
Netplan, resolved, networkd and Docker dependencies. It checks the destination,
saves first-install configuration privately, and runs `netplan generate` plus
systemd daemon reload. It deliberately does not apply Netplan or restart Docker,
resolved, VPN or workers. Apply network changes only under the administrative
rollback watchdog and check the merged Netplan output before application.
The existing networkd renderer and generated interface unit
`10-netplan-ens18.network` are prerequisites; do not apply this script to a
NetworkManager host. DHCP identifiers/MAC are unchanged. DHCPv6 is not enabled by
the overlay; matching overrides prevent future DHCP DNS adoption. Public IPv6
is independently filtered by the VPN firewall.

The destination has now passed the main operator's live **VPN stop** gate:
public HTTP and DNS attempts were blocked and no outgoing physical-interface
packets escaped during that bounded probe. The main operator also verified reboot (SSH, Docker, VPN, firewall and exit IP)
and Docker restart. The first immediate DNS request after Docker restart failed
with curl exit6; a later readiness retry succeeded. These outcomes do not prove
unperformed SIGKILL, endpoint loss or every runtime role. Readiness must pass
after restarts before starting provider operations; never retry a model mutation
merely because a network readiness probe may be retried.
When collecting leakage evidence, use `tcpdump -Q out` on ens18 and count only
nonempty packet lines (not stderr startup/statistics). Incoming LAN multicast
is not an outbound VPN leak; a blank capture output must not be counted as one
packet. Limit capture to expected probe traffic and explicitly separate allowed
LAN/endpoint traffic from prohibited public traffic. Retain the actual capture
filter, test timestamps, command exit results and sanitized counters in evidence.
