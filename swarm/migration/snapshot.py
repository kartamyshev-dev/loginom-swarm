#!/usr/bin/env python3
"""Root-only cold snapshot. Never stops or starts services; failures leave .partial."""
import argparse
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import stat
import subprocess

REQUIRED = ['opt/paperclip/.env', 'opt/paperclip/compose.yaml', 'opt/paperclip/Caddyfile',
 'opt/paperclip/scripts', 'opt/paperclip/systemd', 'opt/paperclip/data/paperclip',
 'opt/paperclip/data/caddy', 'opt/paperclip/data/caddy-config', 'opt/loginom-worker',
 'opt/loginom-swarm', 'etc/loginom-swarm', 'var/lib/loginom-swarm-memory',
 'var/lib/loginom-swarm-publisher']
PATTERNS = ['etc/systemd/system/*paperclip*', 'etc/systemd/system/*loginom*',
 'etc/apparmor.d/*loginom*', 'etc/apparmor.d/local/*loginom*']

def digest(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''): h.update(chunk)
    return h.hexdigest()

def metadata(path, name):
    s = path.lstat()
    kind = 'symlink' if stat.S_ISLNK(s.st_mode) else 'directory' if stat.S_ISDIR(s.st_mode) else 'file' if stat.S_ISREG(s.st_mode) else 'special'
    row = dict(path=name, kind=kind, uid=s.st_uid, gid=s.st_gid, mode=stat.S_IMODE(s.st_mode), mtime_ns=s.st_mtime_ns)
    if kind == 'file': row.update(size=s.st_size, sha256=digest(path))
    if kind == 'symlink': row['target'] = os.readlink(path)
    row['xattrs'] = {key: hashlib.sha256(os.getxattr(path, key, follow_symlinks=False)).hexdigest()
                     for key in os.listxattr(path, follow_symlinks=False)}
    return row

def inventory(root, names):
    rows = {}
    skipped = []
    def visit(name):
        if name in rows: return
        path = root / name
        row = metadata(path, name)
        if row['kind'] == 'special':
            if stat.S_ISSOCK(path.lstat().st_mode):
                skipped.append(name); return
            raise ValueError('Unsupported special file; reconcile before snapshot: ' + name)
        rows[name] = row
        if row['kind'] == 'directory':
            for child in sorted(path.iterdir()): visit(name + '/' + child.name)
    for name in names: visit(name)
    return sorted(rows.values(), key=lambda r: r['path']), skipped

def run(args, **kw):
    # stderr may include private DB details; callers do not publish it.
    return subprocess.run(args, check=True, stderr=subprocess.PIPE, **kw)

def assert_frozen(compose, services):
    for service in services:
        state = run(['systemctl', 'show', service, '--property=ActiveState', '--value'], stdout=subprocess.PIPE).stdout.decode().strip()
        if state not in ('inactive', 'failed'): raise ValueError('Writer/timer not frozen: ' + service)
    active = run(compose + ['ps', '--status', 'running', '--services'], stdout=subprocess.PIPE).stdout.decode().split()
    if 'paperclip' in active: raise ValueError('Paperclip is running')
    if 'db' not in active: raise ValueError('Database must be running for logical dump')

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-hostname', required=True)
    p.add_argument('--source-machine-id', required=True)
    p.add_argument('--output', required=True, type=Path, help='New directory outside all source trees')
    p.add_argument('--service', action='append', default=['loginom-swarm-worker.service', 'loginom-swarm-memory.service', 'paperclip-backup.timer', 'paperclip-backup.service'])
    p.add_argument('--extra-path', action='append', default=[], help='Additional absolute reviewed configuration path')
    a = p.parse_args()
    os.umask(0o077)
    if os.geteuid() != 0: raise ValueError('Must run as root')
    if socket.gethostname() != a.source_hostname or Path('/etc/machine-id').read_text().strip() != a.source_machine_id:
        raise ValueError('Source host identity mismatch')
    names = REQUIRED + [str(x.relative_to('/')) for pattern in PATTERNS for x in Path('/').glob(pattern)]
    for value in a.extra_path:
        q = Path(value)
        if not q.is_absolute() or '..' in q.parts: raise ValueError('Unsafe extra path')
        names.append(str(q.relative_to('/')))
    output = a.output.resolve()
    for name in names:
        source = Path('/') / name
        if not source.exists() and not source.is_symlink(): raise ValueError('Missing required path: ' + name)
        if output == source or source in output.parents: raise ValueError('Output overlaps source')
    compose = ['docker', 'compose', '--project-directory', '/opt/paperclip']
    locks = []
    for name in ['/run/lock/paperclip-backup.lock', '/opt/loginom-worker/state/heavy.lock']:
        f = open(name, 'a'); fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB); locks.append(f)
    assert_frozen(compose, a.service)
    version = run(compose + ['exec', '-T', 'db', 'psql', '-XAt', '-U', 'paperclip', '-d', 'paperclip', '-c', 'SHOW server_version_num'], stdout=subprocess.PIPE).stdout.decode().strip()
    if not version.isdigit() or not 170000 <= int(version) < 180000: raise ValueError('Expected PostgreSQL 17')
    rows, skipped = inventory(Path('/'), names)
    required_space = sum(r.get('size', 0) for r in rows) + 2 * 1024**3
    if shutil.disk_usage(output.parent).free < required_space: raise ValueError('Insufficient snapshot free space')
    partial = output.with_name(output.name + '.partial')
    if output.exists(): raise ValueError('Output already exists')
    partial.mkdir(mode=0o700)  # stale partials are never reused or deleted
    (partial / 'paths.nul').write_bytes(b''.join(r['path'].encode() + b'\0' for r in rows))
    with (partial / 'database.dump').open('wb') as f:
        run(compose + ['exec', '-T', 'db', 'pg_dump', '-U', 'paperclip', '-d', 'paperclip', '-Fc'], stdout=f)
    with (partial / 'database.roles.sql').open('wb') as f:
        run(compose + ['exec', '-T', 'db', 'pg_dumpall', '-U', 'paperclip', '--roles-only'], stdout=f)
    with (partial / 'database.rows.sha256').open('wb') as f:
        run(['/opt/paperclip/scripts/database-fingerprint.sh', 'paperclip'], stdout=f)
    run(['tar', '--create', '--gzip', '--file', str(partial / 'filesystem.tar.gz'), '--directory', '/',
         '--format=pax', '--numeric-owner', '--acls', '--xattrs', '--xattrs-include=*', '--hard-dereference', '--no-recursion',
         '--null', '--verbatim-files-from', '--files-from', str(partial / 'paths.nul')], stdout=subprocess.DEVNULL)
    assert_frozen(compose, a.service)
    fingerprint_after = run(['/opt/paperclip/scripts/database-fingerprint.sh', 'paperclip'], stdout=subprocess.PIPE).stdout
    if fingerprint_after != (partial / 'database.rows.sha256').read_bytes(): raise ValueError('Database changed while snapshotting')
    after, skipped_after = inventory(Path('/'), names)
    if after != rows or skipped_after != skipped: raise ValueError('Source changed while snapshotting')
    (partial / 'paths.nul').unlink()
    manifest = dict(schema=1, complete=True, hostname=a.source_hostname, machineId=a.source_machine_id,
                    createdAt=datetime.datetime.now(datetime.timezone.utc).isoformat(), noRestart=True,
                    files=rows, skippedSockets=skipped,
                    artifacts={f.name: digest(f) for f in partial.iterdir()})
    (partial / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=True, indent=2) + '\n')
    for f in partial.iterdir(): f.chmod(0o600)
    partial.rename(output)
    print(json.dumps({'complete': True, 'files': len(rows), 'output': str(output)}))

if __name__ == '__main__':
    try: main()
    except (ValueError, OSError, subprocess.CalledProcessError) as e:
        raise SystemExit('Snapshot failed (no services restarted): ' + (str(e) if not isinstance(e, subprocess.CalledProcessError) else 'private subprocess failed'))
