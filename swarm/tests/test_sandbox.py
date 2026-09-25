import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'runtime'))
import sandbox


class SandboxTests(unittest.TestCase):
    def row(self,role):
        return {'role':role,'workspace':f'/opt/loginom-worker/workspaces/infrastructure/{role}',
                'profile':f'/opt/loginom-worker/profiles/infrastructure/{role}'}

    def test_reviewer_only_workspace_is_readonly_but_profile_persists(self):
        row=self.row('reviewer')
        with patch.object(sandbox, 'qualified_bwrap', return_value=Path(sandbox.BWRAP)):
            argv,env=sandbox.command(row,['/usr/bin/true'])
        def mounted(flag,path):return any(argv[i:i+3]==[flag,path,path] for i in range(len(argv)))
        self.assertTrue(mounted('--ro-bind',row['workspace']))
        self.assertTrue(mounted('--bind',row['profile']))
        self.assertNotIn('--share-net',argv)
        for forbidden in ['/opt/paperclip','/opt/loginom-worker/state','/run/loginom-swarm','/root','/home']:
            self.assertNotIn(forbidden,argv)
        self.assertNotIn('OPENVIKING_API_KEY',env)

    def test_registration_refuses_traversal_before_reading_config(self):
        for campaign,role in [('../sampling','developer'),('sampling','root'),('/tmp','developer')]:
            with self.assertRaises(ValueError):sandbox.registration(campaign,role)

    def test_writable_registration_rejected_even_if_owner_is_root(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d).resolve()/'roles.json';p.write_text('[]');p.chmod(0o666)
            with self.assertRaises(ValueError):sandbox.immutable_file(p)

    def test_symlink_registration_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d).resolve()/'roles.json';p.write_text('[]')
            link=p.parent/'alias';link.symlink_to(p)
            with self.assertRaises(ValueError):sandbox.immutable_file(link)

    def test_modified_launcher_is_rejected_before_command_construction(self):
        import hashlib
        with tempfile.TemporaryDirectory() as d:
            binary=Path(d)/'bwrap';binary.write_bytes(b'approved-binary')
            approved=hashlib.sha256(binary.read_bytes()).hexdigest()
            with patch.object(sandbox, 'immutable_file', return_value=binary), patch.object(sandbox, 'BWRAP_SHA256', approved):
                self.assertEqual(sandbox.qualified_bwrap(), binary)
                binary.write_bytes(b'modified-binary')
                with self.assertRaisesRegex(ValueError, 'Unqualified'):
                    sandbox.command(self.row('developer'), ['/usr/bin/true'])
