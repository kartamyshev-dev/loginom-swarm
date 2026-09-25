#!/usr/bin/env python3
"""Configure one server CLI profile using stdin; never print credentials."""
import argparse
import json
import shlex
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
p = argparse.ArgumentParser()
p.add_argument("--role", choices=["acceptance", "loginom-development"], required=True)
args = p.parse_args()
values = {}
for line in (ROOT / ".env").read_text().splitlines():
    if "=" in line and not line.lstrip().startswith("#"):
        key, value = line.split("=", 1)
        tokens = shlex.split(value)
        if len(tokens) == 1:
            values[key] = tokens[0]
body = json.dumps({"url": "https://app.loginom.ai", "username": "agent",
                   "password": "", "apiKey": values["LOGINOM_API_KEY"]})
# The role is a closed enum; the secret travels exclusively through stdin.
command = ("cd /opt/loginom-worker/workspaces/sampling/acceptance && "
           "runuser -u loginom-worker -- aa-exec -p loginom-swarm-worker -- env "
           f"LOGINOM_AI_AGENT_CLI_PROFILE=/opt/loginom-worker/profiles/sampling/{args.role} "
           "xvfb-run -a /opt/loginom-worker/.local/bin/loginom-ai-agent-cli "
           "--no-headless loginom setup --stdin-json --format json")
result = subprocess.run([str(ROOT / "swarm/scripts/server.sh"),
                         "-o", "PreferredAuthentications=password", "-o", "PubkeyAuthentication=no", command],
                        input=body, text=True, capture_output=True, timeout=180)
records = []
for line in result.stdout.splitlines():
    try:
        records.append(json.loads(line))
    except ValueError:
        pass
safe = [{key: record[key] for key in ("ok", "code", "state", "hasApiKey", "hasPassword", "failure")
         if key in record} for record in records if isinstance(record, dict)]
print(json.dumps({"role": args.role, "exitCode": result.returncode, "results": safe}))
raise SystemExit(result.returncode)
