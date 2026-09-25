#!/bin/bash
set -euo pipefail
test "$(id -u)" = 0 || { echo 'Run the reviewed installer as the deployment operator.' >&2; exit 1; }
test "$(uname -m)" = x86_64 || { echo 'Only the pinned linux-x64 toolchain is qualified.' >&2; exit 1; }
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y --no-install-recommends bubblewrap apparmor-utils xvfb xauth unzip \
  git gh python3 ca-certificates curl libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 \
  libcups2 libdrm2 libdbus-1-3 libxcb1 libxkbcommon0 libatspi2.0-0 libx11-6 \
  libxcomposite1 libxdamage1 libxext6 libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 \
  libcairo2 libasound2t64 fonts-liberation
runtime=/opt/loginom-swarm/toolchains/20260925.1
if [ -e "$runtime" ]; then
  echo 'Toolchain already exists. Verify the manifest instead of overwriting it.' >&2
  exit 1
fi
install -d -m 755 /opt/loginom-swarm/toolchains
stage=$(mktemp -d /opt/loginom-swarm/toolchains/.prepare-XXXXXX)
# Preserve an incomplete stage after failure for reconciliation. It is never activated.
curl -fsSL --retry 3 https://github.com/gooddaytoday/loginom-ai-agent/releases/download/v0.1.16/loginom-ai-agent-cli-0.1.16-linux-x64.tar.gz -o "$stage/cli.tar.gz"
echo "ac8b763989998e672435af30cf804f4d6807667ae3f9464100a14da1f343e540  $stage/cli.tar.gz" | sha256sum -c -
mkdir "$stage/cli"
tar -xzf "$stage/cli.tar.gz" -C "$stage/cli"
echo "bc17c508ffeed0ec622934f9b7fa72f8e78da65350e63c3eceb56fa688aa5e12  $stage/cli/resources/loginom/bin/node" | sha256sum -c -
curl -fsSL --retry 3 https://github.com/oven-sh/bun/releases/download/bun-v1.3.14/bun-linux-x64.zip -o "$stage/bun.zip"
echo "951ee2aee855f08595aeec6225226a298d3fea83a3dcd6465c09cbccdf7e848f  $stage/bun.zip" | sha256sum -c -
unzip -q "$stage/bun.zip" -d "$stage"
test "$("$stage/bun-linux-x64/bun" -e 'console.log(process.versions.bun + " " + Bun.revision)')" = '1.3.14 0d9b296af33f2b851fcbf4df3e9ec89751734ba4'
rm "$stage/cli.tar.gz" "$stage/bun.zip"
chown -R root:root "$stage"
chmod -R go-w "$stage"
chmod 755 "$stage"
mv "$stage" "$runtime"
echo 'Pinned toolchain installed. No model run or profile activation was performed.'
