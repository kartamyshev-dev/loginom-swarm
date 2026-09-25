#!/usr/bin/env python3
"""Owner API client. Reads local .env; cookies stay in memory; never starts runs."""
import http.cookiejar
import json
import shlex
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class Client:
    def __init__(self):
        values = {}
        for line in (ROOT / '.env').read_text().splitlines():
            if not line.strip() or line.lstrip().startswith('#') or '=' not in line:
                continue
            key, value = line.split('=', 1)
            tokens = shlex.split(value, comments=True)
            if len(tokens) == 1:
                values[key.strip()] = tokens[0]
        self.base = 'https://' + values['PAPERCLIP_DOMAIN']
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.request('POST', '/api/auth/sign-in/email', {
            'email': values['PAPERCLIP_EMAIL'], 'password': values['PAPERCLIP_PASSWORD']})

    def request(self, method, path, data=None):
        if not path.startswith('/api/') or '://' in path:
            raise ValueError('Only relative API paths are accepted')
        req = urllib.request.Request(self.base + path, method=method,
            data=None if data is None else json.dumps(data).encode(),
            headers={'Content-Type': 'application/json', 'Origin': self.base})
        try:
            with self.opener.open(req, timeout=40) as response:
                raw = response.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as error:
            # Do not print server responses: they can contain credentials/config.
            details = error.read()
            diagnostic = ROOT / 'private/last-api-error.json'
            diagnostic.parent.mkdir(mode=0o700, exist_ok=True)
            import os
            fd = os.open(diagnostic, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
            with os.fdopen(fd, 'wb') as output:
                output.write(details)
            raise RuntimeError(f'{method} {path}: HTTP {error.code}; no automatic retry') from None

    def close(self):
        self.request('POST', '/api/auth/sign-out', {})


if __name__ == '__main__':
    client = None
    try:
        client = Client()
        if sys.argv[1:] != ['status']:
            raise ValueError('Usage: paperclip-api.py status')
        for company in client.request('GET', '/api/companies'):
            print(json.dumps({k: company.get(k) for k in ('id', 'name')}, ensure_ascii=False))
    except Exception as error:
        print(str(error) if isinstance(error, (RuntimeError, ValueError)) else type(error).__name__, file=sys.stderr)
        sys.exit(1)
    finally:
        if client:
            client.close()
