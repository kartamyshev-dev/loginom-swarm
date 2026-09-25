import importlib.util
import pathlib
import unittest
from unittest.mock import MagicMock, patch

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / 'scripts/paperclip-api.py'
spec = importlib.util.spec_from_file_location('paperclip_api', SCRIPT)
api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(api)


class ApiOriginTests(unittest.TestCase):
    def test_explicit_http_origin_and_legacy_fallback(self):
        self.assertEqual(api.base_url({'PAPERCLIP_BASE_URL': 'http://loginom-swarm.bg.local',
                                     'PAPERCLIP_DOMAIN': 'old.example'}),
                         'http://loginom-swarm.bg.local')
        self.assertEqual(api.base_url({'PAPERCLIP_DOMAIN': 'old.example'}),
                         'https://old.example')
        for origin in ('http://10.200.4.106', 'http://localhost:3100',
                       'https://paperclip.example', 'http://[::1]:80'):
            self.assertEqual(api.base_url({'PAPERCLIP_BASE_URL': origin}), origin)

    def test_ambiguous_or_credential_bearing_origins_fail_before_network(self):
        for origin in ('', 'ftp://host', '//host', 'http://', 'http://a:b@host',
                       'http://host/', 'http://host/api', 'http://host?q=1',
                       'http://host?', 'http://host#x', 'http://host#',
                       'http://host:bad', 'http://host:', 'http://host:70000',
                       'http://host:0', ' http://host', 'http://ho\nst',
                       'http://host\\other', 'http://ho%73t'):
            with self.subTest(origin=origin), self.assertRaises(ValueError):
                api.base_url({'PAPERCLIP_BASE_URL': origin})

    def test_client_signin_uses_configured_origin_without_network(self):
        env = ('PAPERCLIP_BASE_URL=http://loginom-swarm.bg.local\n'
               'PAPERCLIP_EMAIL=test@example.test\nPAPERCLIP_PASSWORD=fixture\n')
        with patch.object(pathlib.Path, 'read_text', return_value=env), \
                patch.object(api.Client, 'request') as request:
            client = api.Client()
        self.assertEqual(client.base, 'http://loginom-swarm.bg.local')
        request.assert_called_once_with('POST', '/api/auth/sign-in/email',
                                        {'email': 'test@example.test', 'password': 'fixture'})
        self.assertTrue(any(isinstance(h, api.NoRedirect) for h in client.opener.handlers))

    def test_only_api_relative_paths_and_exact_origin_header(self):
        client = api.Client.__new__(api.Client)
        client.base = 'http://loginom-swarm.bg.local'
        client.opener = MagicMock()
        client.opener.open.return_value.__enter__.return_value.read.return_value = b'{}'
        client.request('GET', '/api/companies?limit=1')
        request = client.opener.open.call_args.args[0]
        self.assertEqual(request.full_url, client.base + '/api/companies?limit=1')
        self.assertEqual(request.get_header('Origin'), client.base)
        client.opener.reset_mock()
        for path in ('https://other/api/health', '//other/api/health', '/auth',
                     '/api/../auth', '/api/%2e%2e/auth', '/api/health#x',
                     '/api/health\n', '/api/health\\x'):
            with self.subTest(path=path), self.assertRaises(ValueError):
                client.request('GET', path)
        client.opener.open.assert_not_called()

    def test_redirect_does_not_create_followup_request(self):
        self.assertIsNone(api.NoRedirect().redirect_request(
            None, None, 302, 'Found', {}, 'https://other.example/api'))


if __name__ == '__main__':
    unittest.main()
