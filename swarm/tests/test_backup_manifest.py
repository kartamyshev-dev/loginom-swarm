import importlib.util
import io
import os
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/backup-manifest.py'
spec = importlib.util.spec_from_file_location('backup_manifest', SCRIPT)
manifest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(manifest)


class ManifestTests(unittest.TestCase):
    def fixture(self, root):
        extracted = root / 'extracted'
        for archive in manifest.ARCHIVES:
            base = extracted / archive
            base.mkdir(parents=True)
            secret = base / 'auth.json'
            secret.write_bytes(b'fixture credential, not a real token')
            secret.chmod(0o600)
            with tarfile.open(root / (archive+'.tar'), 'w', format=tarfile.PAX_FORMAT) as out:
                out.add(secret, arcname='auth.json')
        manifest.create(root)
        return extracted

    def test_snapshot_is_independent_of_live_profiles(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            extracted = self.fixture(root)
            manifest.verify(root, extracted)
            data = (root/'snapshot-manifest.json').read_text()
            self.assertNotIn('fixture credential', data)
            self.assertEqual((root/'snapshot-manifest.json').stat().st_mode & 0o777, 0o600)

    def test_changed_credential_and_permissions_fail(self):
        for change in ('content', 'mode'):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                extracted = self.fixture(root)
                file = extracted/'worker/auth.json'
                if change == 'content': file.write_bytes(b'changed')
                else: file.chmod(0o644)
                with self.assertRaises(ValueError):
                    manifest.verify(root, extracted)

    def test_unsafe_archive_path_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with tarfile.open(root/'files.tar', 'w') as out:
                entry = tarfile.TarInfo('../escape')
                entry.size = 1
                out.addfile(entry, io.BytesIO(b'x'))
            with self.assertRaises(ValueError): manifest.create(root)

    def test_acl_is_verified_independently_of_file_mode(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            extracted = self.fixture(root)
            import json
            value = json.loads((root/'snapshot-manifest.json').read_text())
            value['files'][0]['acls'] = {'access': ['group::---', 'other::---', 'user::rw-']}
            (root/'snapshot-manifest.json').write_text(json.dumps(value))
            with patch.object(manifest.subprocess, 'run', return_value=SimpleNamespace(
                    stdout='user::rw-\ngroup::---\nother::---\n')):
                manifest.verify(root, extracted)
            with patch.object(manifest.subprocess, 'run', return_value=SimpleNamespace(
                    stdout='user::rw-\ngroup::r--\nother::---\n')):
                with self.assertRaises(ValueError): manifest.verify(root, extracted)

    @unittest.skipUnless(hasattr(os, 'getxattr'), 'requires xattr support')
    def test_restored_xattr_must_match_snapshot(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            extracted = self.fixture(root)
            import json
            value = json.loads((root/'snapshot-manifest.json').read_text())
            value['files'][0]['xattrs'] = {'user.fixture': '0'*64}
            (root/'snapshot-manifest.json').write_text(json.dumps(value))
            with self.assertRaises((ValueError, OSError)):
                manifest.verify(root, extracted)


if __name__ == '__main__':
    unittest.main()
