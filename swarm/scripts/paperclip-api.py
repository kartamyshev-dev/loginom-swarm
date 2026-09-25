#!/usr/bin/env python3
"""Owner API client. Reads local .env; cookies stay in memory; never starts runs."""
import http.cookiejar
import json
import shlex
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def base_url(values):
    """An explicit origin takes precedence; legacy deployments retain HTTPS."""
    value = values.get('PAPERCLIP_BASE_URL')
    if value is None:
        value = 'https://' + values['PAPERCLIP_DOMAIN']
    try:
        parsed = urllib.parse.urlsplit(value)
        port = parsed.port
        valid = (parsed.scheme in ('http', 'https') and parsed.hostname
                 and parsed.username is None and parsed.password is None
                 and not parsed.path and not parsed.query and not parsed.fragment
                 and '?' not in value and '#' not in value
                 and not parsed.netloc.endswith(':')
                 and (port is None or port > 0)
                 and not any(c.isspace() or ord(c) < 32 or ord(c) == 127
                             for c in value)
                 and '\\' not in value and '%' not in parsed.netloc)
    except ValueError:
        valid = False
    if not valid:
        raise ValueError('Paperclip base URL must be an HTTP(S) origin without credentials, path, query or fragment')
    return value


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never send owner credentials or cookies to a redirected origin.
        return None


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
        self.base = base_url(values)
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()), NoRedirect())
        self.request('POST', '/api/auth/sign-in/email', {
            'email': values['PAPERCLIP_EMAIL'], 'password': values['PAPERCLIP_PASSWORD']})

    def request(self, method, path, data=None):
        parsed = urllib.parse.urlsplit(path)
        if (not path.startswith('/api/') or '://' in path or parsed.fragment
                or '#' in path or '\\' in path
                or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in path)
                or any(part in ('.', '..') for part in
                       urllib.parse.unquote(parsed.path).split('/'))):
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
