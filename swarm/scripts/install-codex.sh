#!/bin/bash
set -euo pipefail
test "$(id -u)" = 0
root=/opt/loginom-swarm/toolchains/codex-0.155.1
test ! -e "$root" || { echo 'Existing Codex toolchain requires verification.' >&2; exit 1; }
node=/opt/loginom-swarm/toolchains/node-v24.19.0-linux-x64/bin/node
npm=/opt/loginom-swarm/toolchains/node-v24.19.0-linux-x64/lib/node_modules/npm/bin/npm-cli.js
mkdir -m 755 "$root"
PATH="$(dirname "$node"):$PATH" "$node" "$npm" install --prefix "$root" --ignore-scripts --omit=dev --no-audit --fund=false --save-exact @openai/codex@0.155.1
chmod -R a+rX,go-w "$root"
ln -s "$root/node_modules/@openai/codex/bin/codex.js" /opt/loginom-swarm/runtime/bin/codex
PATH="/opt/loginom-swarm/runtime/bin:$PATH" /opt/loginom-swarm/runtime/bin/codex --version
