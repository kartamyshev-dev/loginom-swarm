import importlib.util
import io
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest

MIGRATION = Path(__file__).resolve().parents[1] / 'migration'
sys.path.insert(0, str(MIGRATION))
import snapshot
import verify_snapshot


class MigrationSnapshotTests(unittest.TestCase):
    def setUp(self):
        # macOS Python lacks Linux xattr APIs; Linux runs exercise real xattrs.
        from unittest.mock import patch
        if not hasattr(snapshot.os, 'listxattr'):
            self.xattrs = patch.object(snapshot.os, 'listxattr', return_value=[], create=True)
            self.xattrs.start()
            self.addCleanup(self.xattrs.stop)

    def fixture(self, root, entries=None):
        root.mkdir(exist_ok=True)
        source = root / 'source'
        source.mkdir()
        (source / 'value').write_text('private value')
        rows, _ = snapshot.inventory(source, ['value'])
        with tarfile.open(root / 'filesystem.tar.gz', 'w:gz') as archive:
            archive.add(source / 'value', arcname='value')
        for name in verify_snapshot.ARTIFACTS - {'filesystem.tar.gz'}:
            (root / name).write_bytes(b'database-fixture')
        manifest = {'schema': 1, 'complete': True, 'noRestart': True, 'files': rows,
                    'artifacts': {name: snapshot.digest(root / name) for name in verify_snapshot.ARTIFACTS}}
        (root / 'manifest.json').write_text(json.dumps(manifest))
        return manifest, source

    def test_valid_bundle_and_tree(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            manifest, source = self.fixture(root)
            self.assertEqual(verify_snapshot.validate_bundle(root), manifest)
            verify_snapshot.verify_tree(source, manifest)

    def test_corrupted_artifact(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self.fixture(root)
            (root / 'database.dump').write_bytes(b'corrupt')
            with self.assertRaisesRegex(ValueError, 'hash mismatch'):
                verify_snapshot.validate_bundle(root)

    def test_incomplete(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            manifest, _ = self.fixture(root)
            manifest['complete'] = False
            (root / 'manifest.json').write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, 'Incomplete'):
                verify_snapshot.validate_bundle(root)

    def test_tree_hash_mismatch(self):
        with tempfile.TemporaryDirectory() as d:
            manifest, source = self.fixture(Path(d))
            (source / 'value').write_text('changed')
            with self.assertRaisesRegex(ValueError, 'mismatch'):
                verify_snapshot.verify_tree(source, manifest)

    def test_path_guard(self):
        for name in ('/etc/passwd', '../escape', 'a/../../escape', './a', 'a//b', ''):
            with self.subTest(name=name), self.assertRaises(ValueError):
                verify_snapshot.safe_name(name)

    def test_symlink_ancestor_guard(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            manifest, _ = self.fixture(root)
            with tarfile.open(root / 'filesystem.tar.gz', 'w:gz') as archive:
                parent = tarfile.TarInfo('link')
                parent.type = tarfile.SYMTYPE
                parent.linkname = '/tmp'
                archive.addfile(parent)
                child = tarfile.TarInfo('link/file')
                child.size = 1
                archive.addfile(child, io.BytesIO(b'x'))
            manifest['files'] = [dict(path='link', kind='symlink', target='/tmp', uid=0, gid=0, mode=0o644),
                                 dict(path='link/file', kind='file', size=1, uid=0, gid=0, mode=0o644)]
            manifest['artifacts']['filesystem.tar.gz'] = snapshot.digest(root / 'filesystem.tar.gz')
            (root / 'manifest.json').write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, 'ancestor'):
                verify_snapshot.validate_bundle(root)

    def test_inventory_does_not_follow_symlink(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / 'link').symlink_to('/etc')
            rows, _ = snapshot.inventory(root, ['link'])
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]['target'], '/etc')

    def test_frozen_refuses_running_writer(self):
        from unittest.mock import patch
        import subprocess
        with patch.object(snapshot, 'run', return_value=subprocess.CompletedProcess([], 0, stdout=b'active\n')):
            with self.assertRaisesRegex(ValueError, 'not frozen'):
                snapshot.assert_frozen(['docker', 'compose'], ['writer.service'])

    def test_unchanged_owner_never_chown_preserves_capabilities(self):
        from unittest.mock import patch
        rows = [dict(path='opt/loginom-swarm/bin/tool', uid=0, gid=0, kind='file',
                     mode=0o755, xattrs={'security.capability': 'hash'}),
                dict(path='opt/loginom-worker/file', uid=1000, gid=1000, kind='file',
                     mode=0o600, xattrs={}),
                dict(path='opt/paperclip/data/file', uid=1000, gid=1000, kind='file',
                     mode=0o600, xattrs={})]
        changes = verify_snapshot.remap_plan({'files': rows})
        with patch.object(verify_snapshot.os, 'chown') as chown, patch.object(verify_snapshot.os, 'chmod') as chmod:
            verify_snapshot.apply_remap(Path('/staging'), changes)
            chown.assert_called_once_with(Path('/staging/opt/loginom-worker/file'), 21001, 21001, follow_symlinks=False)
            chmod.assert_called_once_with(Path('/staging/opt/loginom-worker/file'), 0o600)

    def test_capability_remap_refused_before_any_extraction_mutation(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as d:
            destination = Path(d).resolve() / 'new'
            manifest = {'files': [dict(path='opt/loginom-worker/tool', uid=1000, gid=0,
                        kind='file', mode=0o755, xattrs={'security.capability': 'hash'})]}
            with patch.object(verify_snapshot.os, 'geteuid', return_value=0), patch.object(verify_snapshot.subprocess, 'run') as run, patch.object(verify_snapshot.os, 'chown') as chown:
                with self.assertRaisesRegex(ValueError, 'Capability-bearing'):
                    verify_snapshot.extract(Path(d), destination, manifest, remap=True)
                self.assertFalse(destination.exists())
                run.assert_not_called()
                chown.assert_not_called()

    def test_inventory_deduplicates_parent_and_explicit_child(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / 'units').mkdir()
            (root / 'units' / 'writer.service').write_text('unit')
            (root / 'unit-link').symlink_to('units/writer.service')
            rows, _ = snapshot.inventory(root, ['units', 'units/writer.service', 'unit-link', 'unit-link'])
            self.assertEqual([r['path'] for r in rows], ['unit-link', 'units', 'units/writer.service'])


if __name__ == '__main__': unittest.main()
