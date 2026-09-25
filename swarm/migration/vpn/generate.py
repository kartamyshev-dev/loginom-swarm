#!/usr/bin/env python3
"""Generate private sing-box 1.12.25 configuration; never print URI/errors containing it."""
import argparse, ipaddress, json, os, pathlib, re, stat, uuid
from urllib.parse import urlsplit, parse_qs, unquote

LAN = ['10.200.0.0/16', '10.150.0.0/22']
BRIDGE = '172.28.0.0/24'

def configuration(uri, endpoint):
    endpoint = str(ipaddress.IPv4Address(endpoint))
    u = urlsplit(uri.strip())
    q = parse_qs(u.query, strict_parsing=True)
    def one(key):
        values = q.get(key, [])
        if len(values) != 1 or not values[0]:
            raise ValueError('missing or duplicate parameter')
        return values[0]
    if not u.hostname or u.port != 443 or not u.username:
        raise ValueError('unsupported endpoint')
    tls = {'enabled':True, 'insecure':False, 'server_name':one('sni'),
           'utls':{'enabled':True,'fingerprint':one('fp')}}
    proxy = {'tag':'proxy','server':endpoint,'server_port':443,
             'bind_interface':'ens18','tls':tls}
    if u.scheme == 'vless':
        if u.password: raise ValueError('invalid VLESS identity')
        identity = str(uuid.UUID(u.username))
        if (one('type'), one('security'), one('encryption'), one('flow')) != ('tcp','reality','none','xtls-rprx-vision'):
            raise ValueError('unsupported transport')
        if not re.fullmatch(r'[A-Za-z0-9_-]{43}', one('pbk')) or not re.fullmatch(r'(?:[a-fA-F0-9]{2}){1,8}', one('sid')):
            raise ValueError('invalid reality parameters')
        proxy.update(type='vless', uuid=identity, flow='xtls-rprx-vision')
        tls['reality']={'enabled':True,'public_key':one('pbk'),'short_id':one('sid')}
    elif u.scheme == 'trojan':
        if (one('type'),one('security')) != ('ws','tls'):
            raise ValueError('unsupported transport')
        if q.get('allowInsecure', ['0']) != ['0'] or q.get('insecure', ['0']) != ['0']:
            raise ValueError('insecure TLS forbidden')
        path, host = one('path'),one('host')
        if not path.startswith('/') or any(c in path + host for c in '\r\n'):
            raise ValueError('invalid websocket parameters')
        proxy.update(type='trojan', password=unquote(u.netloc.rsplit('@',1)[0]),
                     transport={'type':'ws','path':path,'headers':{'Host':host}})
    else:
        raise ValueError('unsupported scheme')
    bypass = LAN + [BRIDGE, '127.0.0.0/8', endpoint + '/32']
    return {
      'log': {'level': 'error', 'timestamp': True},
      'dns': {'servers': [
        {'type':'tls','tag':'public','server':'8.8.8.8','server_port':853,'tls':{'server_name':'dns.google'},'detour':'proxy'},
        {'type':'udp','tag':'corporate','server':'10.200.0.3','server_port':53,'bind_interface':'ens18'}],
        'rules':[{'domain_suffix':['bg.local','basegroup.ru'],'server':'corporate'}],
        'final':'public','strategy':'ipv4_only'},
      'inbounds':[
        {'type':'direct','tag':'dns-host','listen':'127.0.0.1','listen_port':5353},
        {'type':'direct','tag':'dns-docker','listen':'172.28.0.1','listen_port':53},
        {'type':'tun','tag':'tun','interface_name':'swarm-tun','address':['172.30.255.1/30'],
         'mtu':1400,'auto_route':True,'auto_redirect':True,'strict_route':True,'stack':'system',
         'route_exclude_address':bypass,'exclude_uid':[21004]}],
      'outbounds':[proxy, {'type':'direct','tag':'direct'}],
      'route':{'auto_detect_interface':True,'default_domain_resolver':'public',
        'rules':[{'inbound':['dns-host','dns-docker'],'action':'hijack-dns'},
                 {'ip_cidr':LAN + [BRIDGE,'127.0.0.0/8'],'outbound':'direct'}], 'final':'proxy'}}

def firewall(endpoint):
    endpoint = str(ipaddress.IPv4Address(endpoint))
    return f'''table inet swarm_vpn {{
 set lan {{ type ipv4_addr; flags interval; elements = {{ 10.200.0.0/16, 10.150.0.0/22 }} }}
 set nonpublic {{ type ipv4_addr; flags interval; elements = {{ 0.0.0.0/8, 10.0.0.0/8, 100.64.0.0/10, 127.0.0.0/8, 169.254.0.0/16, 172.16.0.0/12, 192.0.0.0/24, 192.0.2.0/24, 192.168.0.0/16, 198.18.0.0/15, 198.51.100.0/24, 203.0.113.0/24, 224.0.0.0/3 }} }}
 chain output {{
  type filter hook output priority 10; policy drop;
  oifname "lo" accept
  ip daddr 127.0.0.1 meta l4proto tcp ct status dnat ct original ip daddr != @nonpublic accept
  meta nfproto ipv4 oifname "swarm-tun" accept
  meta nfproto ipv4 meta l4proto {{ udp, icmp }} meta mark 0x2023 accept
  ip daddr @lan accept
  oifname "br-swarm" ip daddr 172.28.0.0/24 accept
  oifname "ens18" udp sport 68 udp dport 67 accept
  oifname "ens18" meta skuid 21004 ip daddr {endpoint} tcp dport 443 accept
  counter drop
 }}
 chain postrouting {{
  type filter hook postrouting priority 110; policy drop;
  oifname "lo" accept
  meta nfproto ipv4 oifname "swarm-tun" accept
  ip daddr @lan accept
  oifname "br-swarm" ip daddr 172.28.0.0/24 accept
  oifname "ens18" udp sport 68 udp dport 67 accept
  oifname "ens18" meta skuid 21004 ip daddr {endpoint} tcp dport 443 accept
  counter drop
 }}
 chain forward {{
  type filter hook forward priority 10; policy drop;
  meta nfproto ipv4 oifname "swarm-tun" accept
  ip daddr @lan accept
  iifname "br-swarm" oifname "br-swarm" ip daddr 172.28.0.0/24 accept
  ip saddr @lan oifname "br-swarm" ip daddr 172.28.0.0/24 tcp dport 80 accept
  ct state established,related oifname "br-swarm" ip daddr 172.28.0.0/24 accept
  counter drop
 }}
 chain input {{
  type filter hook input priority 10; policy drop;
  iifname "lo" accept
  ct state established,related accept
  iifname "ens18" udp sport 67 udp dport 68 accept
  ip saddr @lan tcp dport {{ 22, 80 }} accept
  iifname "br-swarm" ip saddr 172.28.0.0/24 ip daddr 172.28.0.1 udp dport 53 accept
  iifname "br-swarm" ip saddr 172.28.0.0/24 ip daddr 172.28.0.1 tcp dport 53 accept
  iifname "br-swarm" ip saddr 172.28.0.0/24 ip daddr 172.28.0.1 meta l4proto tcp ct status dnat ct original ip daddr != @nonpublic accept
  counter drop
 }}
}}
'''

def main():
    p=argparse.ArgumentParser(); p.add_argument('--uri-file',required=True); p.add_argument('--endpoint-ip',required=True); p.add_argument('--output',required=True)
    a=p.parse_args()
    try:
        path=pathlib.Path(a.uri_file)
        if path.is_symlink() or stat.S_IMODE(path.stat().st_mode) & 0o077: raise ValueError('unsafe input permissions')
        cfg=configuration(path.read_text(),a.endpoint_ip)
        out=pathlib.Path(a.output); out.mkdir(mode=0o700,parents=True,exist_ok=True)
        if out.is_symlink() or stat.S_IMODE(out.stat().st_mode)&0o077: raise ValueError('unsafe output directory')
        for name,data in [('config.json',json.dumps(cfg,indent=2)+'\n'),('firewall.nft',firewall(a.endpoint_ip))]:
            fd=os.open(out/name,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(fd,'w') as f: f.write(data)
    except (ValueError,OSError,TypeError):
        p.exit(1,'VPN generation failed: check protected input, endpoint, parameters and fresh output directory.\n')
if __name__=='__main__': main()
