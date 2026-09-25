#!/usr/bin/env python3
"""Prepare an update in a separate worktree. Never modifies deployment or swarm."""
import argparse
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def run(*args, cwd=ROOT, check=True):
    return subprocess.run(args, cwd=cwd, text=True, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, check=check)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("tag")
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    if not re.fullmatch(r"v\d{4}\.\d+\.\d+", args.tag):
        p.error("A stable Paperclip tag is required; prereleases and refs are rejected")
    args.output.mkdir(parents=True, exist_ok=True)
    run("git", "fetch", "origin", "swarm")
    # Use the canonical URL even if a developer changed the upstream remote.
    run("git", "fetch", "https://github.com/paperclipai/paperclip.git",
        f"refs/tags/{args.tag}")
    target = run("git", "rev-parse", "FETCH_HEAD^{commit}").stdout.strip()
    prepare(ROOT, args.tag, target, args.output)


def prepare(root, tag, target, output_dir):
    """Isolated merge; injectable repository only for local fixture tests."""
    def run(*args, cwd=None, check=True):
        return subprocess.run(args, cwd=cwd or root, text=True, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, check=check)
    branch = f"update/paperclip-{tag}"
    if run("git", "show-ref", "--verify", f"refs/heads/{branch}", check=False).returncode == 0:
        raise SystemExit("Update branch already exists; inspect it before retrying")
    directory = Path(tempfile.mkdtemp(prefix="loginom-swarm-update-")) / "checkout"
    run("git", "worktree", "add", "-b", branch, str(directory), "origin/swarm")
    old = json.loads((directory / "swarm/upstream.lock.json").read_text())
    result = run("git", "merge", "--no-commit", "--no-ff", target, cwd=directory, check=False)
    conflicts = run("git", "diff", "--name-only", "--diff-filter=U", cwd=directory).stdout.splitlines()
    report = {"tag": tag, "commit": target, "previousCommit": old["commit"],
              "branch": branch, "worktree": str(directory), "conflicts": conflicts,
              "status": "conflict" if conflicts else "prepared" if result.returncode == 0 else "failed",
              "deploymentChanged": False}
    (output_dir / "update-report.json").write_text(json.dumps(report, indent=2) + "\n")
    if result.returncode:
        print(json.dumps(report, indent=2))
        # Retain isolated worktree/index for diagnosis, never abort someone else's merge.
        raise SystemExit(2)
    # Do not silently activate newly introduced or restored upstream workflows.
    workflows = directory / ".github/workflows"
    upstream_paths = run("git", "ls-tree", "-r", "--name-only", target,
                         ".github/workflows", cwd=directory).stdout.splitlines()
    registry_path = directory / "swarm/upstream-changes.json"
    registry = json.loads(registry_path.read_text())
    workflow_entry = next(e for e in registry["changes"] if e["id"] == "SWARM-003")
    workflow_entry["files"] = upstream_paths
    for name in upstream_paths:
        src = directory / name
        if src.exists():
            dst = directory / "swarm/upstream-workflows" / (src.name + ".disabled")
            dst.write_bytes(src.read_bytes())
            src.unlink()
    registry_path.write_text(json.dumps(registry, indent=2) + "\n")
    old.update(tag=tag, commit=target, paperclipVersion=tag[1:])
    (directory / "swarm/upstream.lock.json").write_text(json.dumps(old, indent=2) + "\n")
    report_dir = directory / "doc/loginom-swarm/updates"
    report_dir.mkdir(exist_ok=True)
    # Local path is intentionally excluded from the committed report.
    (report_dir / (tag + ".json")).write_text(json.dumps(
        {k: v for k, v in report.items() if k != "worktree"}, indent=2) + "\n")
    diff = run("git", "diff", "--stat", target, cwd=directory).stdout
    (output_dir / "divergence.txt").write_text(diff)
    run("python3", "swarm/scripts/check-upstream.py", cwd=directory)
    print(json.dumps(report, indent=2))
    if os.getenv("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as output:
            output.write(f"worktree={directory}\nbranch={branch}\n")


if __name__ == "__main__":
    main()
