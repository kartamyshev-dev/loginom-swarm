#!/usr/bin/env python3
"""Root-only, read-only VPS check. Never emits a token or provider response."""
import json
import os
import pwd
import stat
import subprocess
from pathlib import Path

HOME = Path('/var/lib/loginom-swarm-publisher')
USER = 'loginom-publisher'
LOGIN = 'kartamyshev-dev'
REPO = 'gooddaytoday/loginom-ai-agent'


def gh(*args):
    result = subprocess.run(['runuser', '-u', USER, '--', 'env', '-i',
        f'HOME={HOME}', f'GH_CONFIG_DIR={HOME}/.config/gh', 'PATH=/usr/bin:/bin',
        'GH_PROMPT_DISABLED=1', 'gh', *args], capture_output=True, text=True, timeout=40)
    if result.returncode:
        raise RuntimeError('GitHub authentication/access check failed; reauthorize publisher')
    return json.loads(result.stdout)


def main():
    if os.geteuid() != 0:
        raise RuntimeError('Run as root on the VPS')
    uid = pwd.getpwnam(USER).pw_uid
    for path in (HOME, HOME / '.config', HOME / '.config/gh', HOME / '.config/gh/hosts.yml'):
        if path.is_symlink():
            raise RuntimeError('Publisher credential path must not be a symlink')
        info = path.stat()
        if info.st_uid != uid or stat.S_IMODE(info.st_mode) & 0o077:
            raise RuntimeError('Publisher credential permissions are not private')
    user = gh('api', 'user')
    if user.get('login') != LOGIN or user.get('id') != 97161574:
        raise RuntimeError('Wrong GitHub identity; publication must stay blocked')
    repo = gh('api', f'repos/{REPO}')
    if repo.get('full_name') != REPO or not repo.get('permissions', {}).get('push'):
        raise RuntimeError('Target repository push permission missing')
    base = gh('api', f'repos/{REPO}/branches/loginom')
    print(json.dumps({'identity': LOGIN, 'repository': REPO, 'pushPermission': True,
        'baseBranch': base['name'], 'baseHead': base['commit']['sha'],
        'credentialPermissions': 'private', 'publicationTested': False}))


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, OSError, ValueError, KeyError, subprocess.TimeoutExpired) as error:
        print(json.dumps({'status': 'blocked', 'reason': str(error) if isinstance(error, RuntimeError) else type(error).__name__}))
        raise SystemExit(1)
