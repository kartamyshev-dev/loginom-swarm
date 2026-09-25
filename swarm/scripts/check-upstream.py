#!/usr/bin/env python3
"""Require an exact documented entry for every changed upstream-owned path."""
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REQUIRED = {"id", "files", "problem", "extensionRejected", "contracts", "tests",
            "dataImpact", "securityImpact", "upgradeImpact", "reference", "removeWhen"}


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT).decode()


def check(root=ROOT):
    lock = json.loads((root / "swarm/upstream.lock.json").read_text())
    base = lock["commit"]
    subprocess.run(["git", "cat-file", "-e", base + "^{commit}"], cwd=root, check=True)
    original = set(subprocess.check_output(
        ["git", "ls-tree", "-rz", "--name-only", base], cwd=root).decode().split("\0"))
    changed = set(subprocess.check_output(
        ["git", "diff", "--no-renames", "--name-only", "-z", base, "--"], cwd=root).decode().split("\0")) - {""}
    owned = changed & original
    entries = json.loads((root / "swarm/upstream-changes.json").read_text())["changes"]
    documented = set()
    for entry in entries:
        missing = REQUIRED - entry.keys()
        if missing or any(not entry[k] for k in REQUIRED):
            raise ValueError(f"Incomplete registry entry: {entry.get('id')}, missing {sorted(missing)}")
        for name in entry["files"]:
            if name in documented:
                raise ValueError(f"Duplicate registry path: {name}")
            if name not in original:
                raise ValueError(f"Not an upstream path: {name}")
            documented.add(name)
    missing = owned - documented
    if missing:
        raise ValueError("Undocumented upstream changes: " + ", ".join(sorted(missing)))
    return sorted(owned)


if __name__ == "__main__":
    for path in check():
        print(path)
    print("Upstream change registry: PASS")
