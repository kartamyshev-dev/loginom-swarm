"""Execute the backup state machine with isolated fake system commands."""
import json
import os
import pathlib
import subprocess
import tempfile
import unittest

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / 'scripts/backup.sh'
SHIM = r'''#!/usr/bin/env python3
import json, os, pathlib, sys
name=pathlib.Path(sys.argv[0]).name
args=sys.argv[1:]
with open(os.environ['CALLS'], 'a') as f:
 f.write(json.dumps([name]+args)+'\n')
if name=='systemctl':
 if args[0]=='show':
  print('loaded' if 'LoadState' in args else ('active' if args[1].endswith('worker') else 'inactive'))
elif name=='docker':
 if args[:3]==['compose','ps','--all']:
  if os.environ.get('STATE_FAIL')=='1':sys.exit(1)
  print(args[-1])
 elif args[0]=='inspect':
  print(os.environ.get('APP_STATE','exited') if args[-1]=='paperclip' else 'running')
 elif 'pg_dump' in args:
  if os.environ.get('DUMP_FAIL')=='1':sys.exit(1)
  print('dump')
 elif 'pg_dumpall' in args: print('roles')
 elif args[:2]==['compose','images']:print('[]')
elif name=='id':
 print('999' if os.environ.get('UID_COLLISION')=='1' else
       {'loginom-worker':'21001','loginom-publisher':'21002','loginom-memory':'21003'}[args[-1]])
elif name=='pgrep':sys.exit(1)
elif name=='tar':
 pathlib.Path(args[args.index('-cf')+1]).write_text('snapshot')
elif name=='gzip':
 for arg in args:
  p=pathlib.Path(arg);p.rename(str(p)+'.gz')
elif name=='dpkg-query':print('fixture-package\t1.0')
'''


class BackupTests(unittest.TestCase):
    def run_backup(self, **env):
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            for path in ('opt/paperclip/scripts', 'opt/paperclip/data/caddy',
                         'opt/paperclip/data/caddy-config', 'opt/loginom-worker/state',
                         'run/lock', 'bin', 'etc/loginom-swarm-vpn', 'root/.ssh',
                         'usr/local/libexec/swarm-vpn',
                         'etc/systemd/network/10-netplan-ens18.network.d',
                         'etc/systemd/system/docker.service.d'):
                (root / path).mkdir(parents=True)
            (root/'opt/paperclip/compose.override.yaml').write_text('services: {}\n')
            fingerprint = root / 'opt/paperclip/scripts/database-fingerprint.sh'
            fingerprint.write_text('#!/bin/sh\nprintf "%064d\\n" 0\n')
            fingerprint.chmod(0o700)
            helper = root / 'opt/paperclip/scripts/backup-manifest.py'
            helper.write_text('#!/bin/sh\nprintf \'{"version":1,"files":[]}\\n\' > "$2/snapshot-manifest.json"\n')
            helper.chmod(0o700)
            for name in ('systemctl', 'docker', 'flock', 'id', 'pgrep', 'tar', 'gzip', 'dpkg-query'):
                shim = root / 'bin' / name
                shim.write_text(SHIM)
                shim.chmod(0o700)
            source = SCRIPT.read_text()
            for prefix in ('/opt/', '/run/', '/etc/systemd/', '/etc/apparmor.d/',
                           '/etc/sysctl.d/', '/etc/modules-load.d/'):
                source = source.replace(prefix, str(root) + prefix)
            source = source.replace('"/$path"', '"' + str(root) + '/$path"')
            script = root / 'backup.sh'
            script.write_text(source)
            calls = root / 'calls.jsonl'
            result = subprocess.run(['bash', str(script)], capture_output=True, text=True,
                                    env={**os.environ, 'PATH': str(root/'bin')+':'+os.environ['PATH'],
                                         'CALLS': str(calls), **env})
            events = [json.loads(line) for line in calls.read_text().splitlines()]
            ready = [p.name for p in (root/'opt/paperclip/backups').iterdir()
                     if not p.name.startswith('.')]
            return result, events, ready

    def test_stopped_app_stays_stopped_and_archives_cover_runtime(self):
        result, events, ready = self.run_backup()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(ready), 1)
        starts = [e for e in events if e[:3] == ['docker', 'compose', 'start']]
        self.assertEqual(starts, [['docker', 'compose', 'start', 'caddy']])
        self.assertIn(['systemctl', 'start', 'loginom-swarm-worker'], events)
        self.assertNotIn(['systemctl', 'start', 'loginom-swarm-memory'], events)
        archives = [e for e in events if e[0] == 'tar']
        worker = next(e for e in archives if any(a.endswith('/worker.tar') for a in e))
        for path in ('opt/loginom-worker', 'opt/loginom-swarm', 'etc/loginom-swarm',
                     'var/lib/loginom-swarm-memory', 'var/lib/loginom-swarm-publisher'):
            self.assertIn(path, worker)
        self.assertFalse(any('node_modules' in arg or '*.log' in arg for arg in worker))
        files = next(e for e in archives if any(a.endswith('/files.tar') for a in e))
        self.assertIn('compose.override.yaml', files)
        self.assertIn('data/caddy', files)
        self.assertIn('data/caddy-config', files)
        self.assertNotIn('backups', files)
        secrets = next(e for e in archives if any(a.endswith('/secrets.tar') for a in e))
        self.assertIn('etc/loginom-swarm-vpn', secrets)
        self.assertIn('root/.ssh', secrets)
        for path in ('usr/local/libexec/swarm-vpn',
                     'etc/systemd/network/10-netplan-ens18.network.d',
                     'etc/systemd/system/docker.service.d'):
            self.assertIn(path, secrets)
        for archive in archives:
            for flag in ('--acls', '--xattrs', '--xattrs-include=*', '--numeric-owner'):
                self.assertIn(flag, archive)
        stop = events.index(['systemctl', 'stop', 'loginom-swarm-worker'])
        self.assertTrue(all(events.index(e) > stop for e in archives))
        compression = next(i for i,e in enumerate(events) if e[0]=='gzip')
        restart = events.index(['systemctl', 'start', 'loginom-swarm-worker'])
        self.assertGreater(compression, restart)

    def test_initial_state_query_failure_never_stops_or_claims_success(self):
        result, events, ready = self.run_backup(STATE_FAIL='1')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(ready, [])
        self.assertNotIn('Backup completed', result.stdout)
        self.assertFalse(any(e[0]=='systemctl' and e[1] in ('start','stop') for e in events))

    def test_dump_failure_restores_only_previously_running_services(self):
        result, events, ready = self.run_backup(DUMP_FAIL='1')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(ready, [])
        self.assertIn(['docker', 'compose', 'start', 'caddy'], events)
        self.assertFalse(any(e[:3]==['docker','compose','start'] and 'paperclip' in e for e in events))
        self.assertNotIn('Backup completed', result.stdout)

    def test_source_uid_collision_is_rejected_before_stopping_services(self):
        result, events, ready = self.run_backup(UID_COLLISION='1')
        self.assertEqual(result.returncode, 75)
        self.assertEqual(ready, [])
        self.assertFalse(any(e[0] in ('docker', 'systemctl', 'tar') for e in events))
        self.assertIn('dedicated LAN service UIDs', result.stdout)

    def test_running_app_is_restored(self):
        result, events, ready = self.run_backup(APP_STATE='running')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(['docker', 'compose', 'start', 'paperclip', 'caddy'], events)


if __name__ == '__main__':
    unittest.main()
