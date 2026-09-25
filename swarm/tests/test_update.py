import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

FILE=Path(__file__).resolve().parents[1]/'scripts/update-upstream.py'
spec=importlib.util.spec_from_file_location('update',FILE)
update=importlib.util.module_from_spec(spec);spec.loader.exec_module(update)


class UpdateTests(unittest.TestCase):
    def test_merge_conflict_stays_in_isolated_worktree_and_reports_paths(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'repo';root.mkdir();out=Path(d)/'report';out.mkdir()
            def git(*args):return subprocess.check_output(['git',*args],cwd=root,stderr=subprocess.DEVNULL,text=True).strip()
            git('init');git('config','user.name','Fixture');git('config','user.email','fixture@example.invalid')
            (root/'contract.txt').write_text('base\n');git('add','.');git('commit','-m','base')
            base=git('rev-parse','HEAD');git('checkout','-b','upstream-fixture')
            (root/'contract.txt').write_text('upstream-change\n');git('commit','-am','upstream');target=git('rev-parse','HEAD')
            git('checkout','-b','swarm',base)
            (root/'swarm').mkdir();(root/'swarm/upstream.lock.json').write_text(json.dumps({'commit':base}))
            (root/'contract.txt').write_text('downstream-change\n');git('add','.');git('commit','-m','fork')
            head=git('rev-parse','HEAD');git('update-ref','refs/remotes/origin/swarm',head)
            try:
                with self.assertRaises(SystemExit) as error:update.prepare(root,'v2026.916.2',target,out)
                self.assertEqual(error.exception.code,2)
                report=json.loads((out/'update-report.json').read_text())
                self.assertEqual(report['status'],'conflict');self.assertEqual(report['conflicts'],['contract.txt'])
                self.assertFalse(report['deploymentChanged'])
                self.assertEqual(git('rev-parse','HEAD'),head);self.assertEqual(git('status','--porcelain'),'')
            finally:
                if (out/'update-report.json').exists():
                    path=Path(json.loads((out/'update-report.json').read_text())['worktree'])
                    git('worktree','remove','--force',str(path));shutil.rmtree(path.parent)

    def test_successful_merge_archives_new_workflows_and_preserves_main_branch(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'repo';root.mkdir();out=Path(d)/'report';out.mkdir()
            def git(*args):return subprocess.check_output(['git',*args],cwd=root,stderr=subprocess.DEVNULL,text=True).strip()
            git('init');git('config','user.name','Fixture');git('config','user.email','fixture@example.invalid')
            (root/'contract.txt').write_text('base\n');git('add','.');git('commit','-m','base')
            base=git('rev-parse','HEAD');git('checkout','-b','upstream-fixture')
            (root/'contract.txt').write_text('compatible-upstream\n')
            (root/'.github/workflows').mkdir(parents=True)
            (root/'.github/workflows/new-release.yml').write_text('name: must-not-run\n')
            git('add','.');git('commit','-m','upstream');target=git('rev-parse','HEAD')
            git('checkout','-b','swarm',base)
            (root/'swarm/scripts').mkdir(parents=True)
            (root/'swarm/upstream-workflows').mkdir()
            # Keep otherwise-empty archive directory in the Git fixture.
            (root/'swarm/upstream-workflows/.keep').write_text('')
            (root/'doc/loginom-swarm').mkdir(parents=True)
            (root/'doc/loginom-swarm/README.md').write_text('fixture')
            shutil.copy(FILE.parent/'check-upstream.py',root/'swarm/scripts/check-upstream.py')
            entry={key:'fixture' for key in ['problem','extensionRejected','contracts','tests','dataImpact','securityImpact','upgradeImpact','reference','removeWhen']}
            entry.update(id='SWARM-003',files=[])
            (root/'swarm/upstream-changes.json').write_text(json.dumps({'changes':[entry]}))
            (root/'swarm/upstream.lock.json').write_text(json.dumps({'commit':base}))
            git('add','.');git('commit','-m','fork');head=git('rev-parse','HEAD')
            git('update-ref','refs/remotes/origin/swarm',head)
            try:
                update.prepare(root,'v2026.916.2',target,out)
                report=json.loads((out/'update-report.json').read_text());path=Path(report['worktree'])
                self.assertEqual(report['status'],'prepared')
                self.assertEqual((path/'contract.txt').read_text(),'compatible-upstream\n')
                self.assertFalse((path/'.github/workflows/new-release.yml').exists())
                self.assertTrue((path/'swarm/upstream-workflows/new-release.yml.disabled').exists())
                self.assertEqual(json.loads((path/'swarm/upstream.lock.json').read_text())['commit'],target)
                self.assertEqual(git('rev-parse','HEAD'),head);self.assertEqual(git('status','--porcelain'),'')
            finally:
                if (out/'update-report.json').exists():
                    path=Path(json.loads((out/'update-report.json').read_text())['worktree'])
                    git('worktree','remove','--force',str(path));shutil.rmtree(path.parent)
