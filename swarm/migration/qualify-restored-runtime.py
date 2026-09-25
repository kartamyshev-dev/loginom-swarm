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
const fs = require('node:fs');
const { chromium } = require('/opt/loginom-swarm/toolchains/20260925.1/cli/resources/loginom/runtime/client/node_modules/playwright');
(async () => {
 let browser;
 try {
  browser = await chromium.launch({executablePath: CHROME_PLACEHOLDER,
   headless: false, chromiumSandbox: true, timeout: 30000,
   env: {...process.env, XDG_CONFIG_HOME:'/tmp/swarm-browser-config', XDG_CACHE_HOME:'/tmp/swarm-browser-cache'}});
  const page = await browser.newPage();
  await page.goto('about:blank');
  const blank = await page.content();
  await page.goto('chrome://sandbox');
  const text = (await page.locator('body').innerText()).replace(/\s+/g,' ');
  const result = {nonRoot: process.getuid() !== 0,
   appArmorEnforced: fs.readFileSync('/proc/self/attr/current','utf8').trim() === 'loginom-swarm-worker (enforce)',
   aboutBlank: blank.includes('<html') && blank.includes('<body'),
   sandboxStatusPage: text.includes('Sandbox'),
   namespaceSandbox: /(?:PID namespaces|Namespace sandbox)\s+Yes\b/.test(text),
   seccompSandbox: /Seccomp-BPF sandbox\s+Yes\b/.test(text)};
  console.log(JSON.stringify(result));
  if (!Object.values(result).every(Boolean)) process.exitCode=1;
 } catch (error) { console.error(String(error)); process.exitCode=1; }
 finally { if (browser) await browser.close(); }
})();
'''.replace('CHROME_PLACEHOLDER', json.dumps(CHROME))


def offline(record, payload, timeout):
    guard = "from pathlib import Path; import os,sys; assert Path('/proc/self/attr/current').read_text().strip() == 'loginom-swarm-worker (enforce)'; os.execv(sys.argv[1], sys.argv[1:])"
    argv, env = command(record, ['/usr/bin/python3', '-I', '-c', guard, *payload], network=False)
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
    if label not in ('loginom-swarm-worker (enforce)', 'loginom-swarm-worker//&unconfined (enforce)'):
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
        result = offline(record, ['/usr/bin/xvfb-run', '-a', '/opt/loginom-swarm/toolchains/20260925.1/cli/resources/loginom/bin/node', '-e', BROWSER_PROBE], 95)
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
