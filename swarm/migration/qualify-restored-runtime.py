#!/usr/bin/python3 -I
"""Offline restored-role probes. No inference, Loginom tools, hooks or profile writes.

Run as loginom-worker under the loginom-swarm-worker AppArmor profile. The normal
worker RPC isolation probe is a separate prerequisite. Only sanitized booleans
are emitted; Chromium uses a disposable profile inside the sandbox's /tmp.
"""
import fcntl
import json
import os
from pathlib import Path
import pwd
import subprocess
import sys

sys.path.insert(0, '/opt/loginom-swarm/runtime')
from sandbox import command, registration

CHROME = ('/opt/loginom-worker/.local/share/loginom-ai-agent-cli/0.1.16-prod/'
          'resources/loginom/browsers/chromium-1243/chrome-linux64/chrome')

BROWSER_PROBE = r'''
import json, os, re, subprocess
from html.parser import HTMLParser

class Text(HTMLParser):
    def __init__(self): super().__init__(); self.parts=[]
    def handle_data(self, value): self.parts.append(value)

chrome = CHROME_PLACEHOLDER
base = [chrome, '--headless=new', '--no-first-run', '--no-default-browser-check',
        '--disable-background-networking', '--disable-component-update',
        '--user-data-dir=/tmp/swarm-chromium-probe', '--dump-dom']
blank = subprocess.run(base + ['about:blank'], capture_output=True, text=True, timeout=40)
sandbox = subprocess.run(base + ['chrome://sandbox'], capture_output=True, text=True, timeout=40)
parser=Text(); parser.feed(sandbox.stdout)
text=' '.join(' '.join(parser.parts).split())
result = {
    'nonRoot': os.getuid() != 0,
    'aboutBlank': blank.returncode == 0 and '<html' in blank.stdout and '<body' in blank.stdout,
    'sandboxStatusPage': sandbox.returncode == 0,
    'namespaceSandbox': bool(re.search(r'(?:PID namespaces|Namespace sandbox)\s+Yes\b', text)),
    'seccompSandbox': bool(re.search(r'Seccomp-BPF sandbox\s+Yes\b', text)),
}
print(json.dumps(result))
raise SystemExit(0 if all(result.values()) else 1)
'''.replace('CHROME_PLACEHOLDER', repr(CHROME))


def offline(record, payload, timeout):
    argv, env = command(record, payload, network=False)
    # Protect persistent profiles and workspaces even if a future CLI status
    # command attempts incidental writes. Sealed overlays remain read-only.
    for i in range(len(argv) - 2):
        if argv[i] == '--bind' and argv[i + 1] in (record['profile'], record['workspace']):
            argv[i] = '--ro-bind'
    return subprocess.run(argv, env=env, capture_output=True, text=True, timeout=timeout)


def main():
    if os.getuid() == 0 or os.getuid() != pwd.getpwnam('loginom-worker').pw_uid:
        raise ValueError('Expected dedicated worker identity')
    label = Path('/proc/self/attr/current').read_text().strip()
    if label != 'loginom-swarm-worker (enforce)':
        raise ValueError('Expected enforced worker AppArmor profile')
    results = {}
    with open('/opt/loginom-worker/state/heavy.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for role in ('developer', 'reviewer'):
            record = registration('sampling', role)
            result = offline(record, ['/opt/loginom-swarm/runtime/bin/codex', 'login', 'status'], 30)
            results[role] = {'localChatGPTOAuthStatus': result.returncode == 0 and
                            'Logged in using ChatGPT' in result.stdout + result.stderr}
        record = registration('sampling', 'acceptance')
        result = offline(record, ['/usr/bin/python3', '-I', '-c', BROWSER_PROBE], 95)
        browser = json.loads(result.stdout)
        if not isinstance(browser, dict) or not browser or any(type(v) is not bool for v in browser.values()):
            raise ValueError('Unexpected probe output')
        results['chromium'] = browser
        passed = result.returncode == 0 and all(all(row.values()) for row in results.values())
        print(json.dumps({'status': 'pass' if passed else 'blocked', 'checks': results,
                          'networkEnabled': False, 'inferenceStarted': False,
                          'loginomConnected': False, 'profilesReadOnly': True,
                          'providerTokenValidityTested': False}))
        return 0 if passed else 1


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, subprocess.TimeoutExpired):
        print(json.dumps({'status': 'blocked', 'reason': 'offline_runtime_probe_failed',
                          'inferenceStarted': False, 'loginomConnected': False}))
        raise SystemExit(1)
