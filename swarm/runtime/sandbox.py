#!/usr/bin/python3 -I
"""Host sandbox construction. Models cannot choose mounts or a host command."""
import json
import os
from pathlib import Path
import re
import stat
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from environment import model_environment

ROOT = Path('/opt/loginom-worker')
TOOLS = Path('/opt/loginom-swarm/toolchains/20260925.1')
ROLE_NAMES = {'developer', 'reviewer', 'acceptance'}


def immutable_file(path):
    path = Path(path)
    if path.resolve(strict=True) != path:
        raise ValueError('Symlink in operator configuration')
    for p in [path, *path.parents]:
        info = p.lstat()
        if info.st_uid != 0 or info.st_mode & 0o022:
            raise ValueError('Operator configuration is not immutable')
    if not stat.S_ISREG(path.stat().st_mode):
        raise ValueError('Expected regular operator configuration')
    return path


def registration(campaign, role, config='/etc/loginom-swarm/roles.json'):
    if not re.fullmatch('[a-z0-9_-]{1,64}', campaign) or role not in ROLE_NAMES:
        raise ValueError('Unknown campaign or role')
    records = json.loads(immutable_file(config).read_text())
    rows = [r for r in records if r['campaign'] == campaign and r['role'] == role]
    if len(rows) != 1:
        raise ValueError('No unique operator registration')
    row = rows[0]
    for name, category in [('profile', 'profiles'), ('workspace', 'workspaces')]:
        path = ROOT / category / campaign / role
        if row[name] != str(path) or path.resolve(strict=True) != path or not path.is_dir():
            raise ValueError('Noncanonical or missing registered directory')
        if path.stat().st_uid != os.getuid():
            raise ValueError('Incorrect role directory owner')
    return row


def command(record, payload, *, network=False):
    """Payload comes only from operator code, never from RPC or model arguments.

    Use a fresh root and PID namespace. No host /run, /home, /root, /opt/paperclip,
    Docker socket, other profiles, or coordinator state are mounted.
    """
    profile, workspace = record['profile'], record['workspace']
    args = ['/usr/bin/bwrap', '--die-with-parent', '--new-session', '--unshare-all']
    if network:
        args.append('--share-net')
    args += ['--cap-drop', 'ALL', '--ro-bind', '/usr', '/usr']
    for name in ['bin', 'sbin', 'lib', 'lib64']:
        if Path('/' + name).exists():
            args += ['--symlink', 'usr/' + name, '/' + name]
    args += ['--proc', '/proc', '--dev', '/dev', '--tmpfs', '/tmp', '--tmpfs', '/run',
             '--dir', '/etc', '--dir', '/dev/shm', '--tmpfs', '/dev/shm']
    for path in ['/etc/ssl', '/etc/ca-certificates', '/etc/resolv.conf', '/etc/hosts',
                 '/etc/nsswitch.conf', '/etc/passwd', '/etc/group', '/etc/fonts']:
        if Path(path).exists():
            args += ['--ro-bind', path, path]
    args += ['--ro-bind', str(TOOLS), str(TOOLS),
             '--ro-bind', '/opt/loginom-swarm/runtime', '/opt/loginom-swarm/runtime',
             '--bind', profile, profile,
             '--ro-bind' if record['role'] == 'reviewer' else '--bind', workspace, workspace,
             '--chdir', workspace, '--', *payload]
    return args, model_environment({}, record['role'], profile)


PROBE = r'''
import json, os, pathlib, subprocess
p = pathlib.Path(os.environ['HOME'])
w = pathlib.Path.cwd()
role = w.name
checks = {
 'uid': os.getuid() != 0,
 'control_plane_hidden': not pathlib.Path('/opt/paperclip').exists(),
 'control_socket_hidden': not pathlib.Path('/run/loginom-swarm/control.sock').exists(),
 'docker_hidden': not pathlib.Path('/var/run/docker.sock').exists(),
 'host_root_hidden': not pathlib.Path('/root').exists(),
 'worker_state_hidden': not pathlib.Path('/opt/loginom-worker/state').exists(),
 'foreign_profiles_hidden': all(not (p.parent/r).exists() for r in ['developer','reviewer','acceptance'] if r != role),
 'private_pid_namespace': len([x for x in pathlib.Path('/proc').iterdir() if x.name.isdigit()]) < 12,
 'secret_environment_removed': not any(x in os.environ for x in ['SERVER_PASSWORD','PAPERCLIP_API_KEY','DATABASE_URL','OPENVIKING_API_KEY']),
}
f=w/'.swarm-write-probe'
try:
 f.write_text('probe')
 checks['workspace_write_policy'] = role != 'reviewer'
 f.unlink()
except OSError:
 checks['workspace_write_policy'] = role == 'reviewer'
f=p/'.swarm-profile-probe'
f.write_text('persistent-profile-probe')
checks['profile_writable'] = f.read_text() == 'persistent-profile-probe'
f.unlink()
print(json.dumps(checks))
raise SystemExit(0 if all(checks.values()) else 1)
'''
