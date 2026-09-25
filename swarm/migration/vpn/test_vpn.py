import importlib.util, pathlib, unittest, tempfile, subprocess, sys, os
s=importlib.util.spec_from_file_location('generate', pathlib.Path(__file__).with_name('generate.py'))
g=importlib.util.module_from_spec(s); s.loader.exec_module(g)
URI='vless://11111111-1111-4111-8111-111111111111@example.test:443?encryption=none&flow=xtls-rprx-vision&fp=chrome&pbk='+('a'*43)+'&security=reality&sid=12345678&sni=example.test&type=tcp#XHTTP-label'
TROJAN='trojan://test%3Apassword%40safe@example.test:443?security=tls&type=ws&path=%2Fsocket&host=example.test&sni=example.test&fp=chrome'
class Configuration(unittest.TestCase):
 def test_trojan_subscription(self):
  out=g.configuration(TROJAN,'185.21.15.251')['outbounds'][0]
  self.assertEqual(out['password'],'test:password@safe')
  self.assertEqual(out['transport'],{'type':'ws','path':'/socket','headers':{'Host':'example.test'}})
  self.assertFalse(out['tls']['insecure']); self.assertEqual(out['type'],'trojan')
 def test_trojan_password_full_userinfo(self):
  uri=TROJAN.replace('test%3Apassword%40safe','test:password')
  self.assertEqual(g.configuration(uri,'185.21.15.251')['outbounds'][0]['password'],'test:password')
 def test_trojan_no_insecure_tls(self):
  with self.assertRaises(ValueError): g.configuration(TROJAN+'&allowInsecure=1','185.21.15.251')
 def test_output_redirect_does_not_require_oif_loopback(self):
  out=g.firewall('185.21.15.251').split('chain output')[1].split('chain forward')[0]
  self.assertIn('ip daddr 127.0.0.1 meta l4proto tcp ct status dnat ct original ip daddr != @nonpublic accept',out)

 def test_transport_not_label(self):
  c=g.configuration(URI,'198.51.100.2'); self.assertEqual(c['outbounds'][0]['type'],'vless'); self.assertNotIn('transport', c['outbounds'][0])
 def test_refuse_ambiguous_or_wrong_transport(self):
  for uri in [URI.replace('type=tcp','type=xhttp'), URI.replace('type=tcp','type=tcp&type=xhttp'), URI.replace('security=reality','security=none')]:
   with self.assertRaises(ValueError): g.configuration(uri,'198.51.100.2')
 def test_corporate_dns_has_direct_dialer_not_empty_detour(self):
  c=g.configuration(URI,'198.51.100.2')['dns']['servers'][1]
  self.assertEqual(c['bind_interface'],'ens18'); self.assertNotIn('detour',c)
 def test_no_public_dns_direct(self):
  c=g.configuration(URI,'198.51.100.2'); self.assertEqual(c['dns']['servers'][0]['detour'],'proxy'); self.assertEqual(c['dns']['final'],'public')
 def test_firewall_not_established_output_or_ipv6_tunnel(self):
  f=g.firewall('198.51.100.2'); out=f.split('chain output')[1].split('chain forward')[0]
  self.assertNotIn('established',out); self.assertIn('meta skuid 21004',out); self.assertIn('meta nfproto ipv4 oifname "swarm-tun"',out)
 def test_injection_refused(self):
  with self.assertRaises(ValueError): g.firewall('1.1.1.1; flush ruleset')
 def test_no_shared_ssh_or_domain_bypass(self):
  c=g.configuration(URI,'198.51.100.2')
  for r in c['route']['rules']: self.assertNotIn('port',r); self.assertNotIn('domain_suffix',r)
 def test_unmarked_docker_tcp_redirect_has_tight_exception(self):
  f=g.firewall('198.51.100.2'); inp=f.split('chain input')[1]
  self.assertNotIn('meta mark', inp)
  self.assertIn('iifname "br-swarm" ip saddr 172.28.0.0/24 ip daddr 172.28.0.1 meta l4proto tcp ct status dnat ct original ip daddr != @nonpublic accept',inp)
  self.assertIn('127.0.0.0/8',f); self.assertIn('172.16.0.0/12',f)
 def test_vpn_config_outside_restored_source_tree(self):
  root=pathlib.Path(__file__).parent
  for name in ['install.sh','install-network.sh','load-firewall','swarm-vpn.service']:
   text=(root/name).read_text()
   self.assertIn('/etc/loginom-swarm-vpn',text)
   self.assertNotIn('/etc/loginom-swarm/vpn',text)
 def test_network_installer_preserves_activation_boundary(self):
  script=pathlib.Path(__file__).with_name('install-network.sh').read_text()
  self.assertIn('netplan generate',script)
  self.assertNotIn('netplan apply',script)
  self.assertNotIn('systemctl restart',script)
  self.assertIn('DNSDefaultRoute=no',script)
  self.assertIn('Requires=swarm-vpn-firewall.service',script)
  self.assertIn('use-dns: false',script)
 def test_marked_udp_requires_postrouting_egress_boundary(self):
  rules=g.firewall('185.21.15.251')
  output=rules.split('chain output')[1].split('chain postrouting')[0]
  post=rules.split('chain postrouting')[1].split('chain forward')[0]
  self.assertIn('meta nfproto ipv4 meta l4proto { udp, icmp } meta mark 0x2023 accept', output)
  self.assertIn('hook postrouting priority 110; policy drop;', post)
  self.assertNotIn('meta mark', post)
  self.assertNotIn('established', post)
  self.assertIn('meta skuid 21004 ip daddr 185.21.15.251 tcp dport 443 accept',post)
  self.assertIn('meta nfproto ipv4 oifname "swarm-tun" accept',post)
  self.assertIn('ip daddr @lan accept',post)
 def test_private_file_and_redacted_errors(self):
  with tempfile.TemporaryDirectory() as d:
   src=pathlib.Path(d)/'uri'; src.write_text(URI); src.chmod(0o644)
   result=subprocess.run([sys.executable, str(pathlib.Path(__file__).with_name('generate.py')), '--uri-file', str(src), '--endpoint-ip', '198.51.100.2', '--output', str(pathlib.Path(d)/'out')],capture_output=True,text=True)
   self.assertNotEqual(result.returncode,0); self.assertNotIn(URI,result.stdout+result.stderr)
 def test_generated_secret_mode(self):
  with tempfile.TemporaryDirectory() as d:
   src=pathlib.Path(d)/'uri'; src.write_text(URI); src.chmod(0o600)
   out=pathlib.Path(d)/'out'
   result=subprocess.run([sys.executable, str(pathlib.Path(__file__).with_name('generate.py')), '--uri-file', str(src), '--endpoint-ip', '198.51.100.2', '--output', str(out)],capture_output=True,text=True)
   self.assertEqual(result.returncode,0,result.stderr)
   self.assertEqual((out/'config.json').stat().st_mode & 0o777,0o600)
   self.assertEqual(out.stat().st_mode & 0o777,0o700)
if __name__=='__main__': unittest.main()
