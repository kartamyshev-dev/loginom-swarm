#!/bin/bash
# Called only inside the infrastructure/build role sandbox by the operator.
set -euo pipefail
umask 077
expected=${1:?Pinned source commit required}
[[ "$expected" =~ ^[a-f0-9]{40}$ ]] || exit 2
work=/opt/loginom-worker/workspaces/infrastructure/developer
cd "$work"
if [ ! -e source ]; then
  git clone --no-checkout https://github.com/gooddaytoday/loginom-ai-agent.git source
  git -C source checkout --detach "$expected"
fi
cd source
test -d .git
git diff --quiet
git diff --cached --quiet
test "$(git rev-parse HEAD)" = "$expected"
export HUSKY=0 PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1
bun install --frozen-lockfile
export LOGINOM_AI_AGENT_NODE_SOURCE=/opt/loginom-swarm/toolchains/node-v24.19.0-linux-x64/bin/node
export LOGINOM_AI_AGENT_BROWSER_SOURCE=/opt/loginom-swarm/toolchains/20260925.1/cli/resources/loginom/browsers
export LOGINOM_AI_AGENT_CHANNEL=dev
bun run packages/loginom-host/script/build-cli.ts "$work/cli-candidate"
test -f "$work/cli-candidate/cli-manifest.json"
python3 - "$work/cli-candidate/cli-manifest.json" "$expected" <<'PY'
import json,sys
m=json.load(open(sys.argv[1]))
assert m['sourceCommit']==sys.argv[2] and m['sourceDirty'] is False
print('CLI_CANDIDATE_BUILD_PASS')
PY
