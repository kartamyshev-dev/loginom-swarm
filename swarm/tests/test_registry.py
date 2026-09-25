import importlib.util
import json
import pathlib
import subprocess
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("registry", pathlib.Path(__file__).resolve().parents[1] / "scripts/check-upstream.py")
registry = importlib.util.module_from_spec(spec)
spec.loader.exec_module(registry)


class RegistryTests(unittest.TestCase):
    def test_rename_cannot_hide_undocumented_upstream_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            def git(*args):
                return subprocess.check_output(["git", *args], cwd=root, stderr=subprocess.DEVNULL).decode().strip()
            git("init")
            git("config", "user.name", "Test")
            git("config", "user.email", "test@example.invalid")
            (root / "original.txt").write_text("upstream\n")
            git("add", ".")
            git("commit", "-m", "base")
            base = git("rev-parse", "HEAD")
            (root / "swarm").mkdir()
            (root / "swarm/upstream.lock.json").write_text(json.dumps({"commit": base}))
            (root / "swarm/upstream-changes.json").write_text('{"changes": []}')
            (root / "original.txt").rename(root / "swarm/original.txt")
            with self.assertRaisesRegex(ValueError, "Undocumented.*original.txt"):
                registry.check(root)


if __name__ == "__main__":
    unittest.main()
