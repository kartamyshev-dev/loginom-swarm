#!/bin/bash
set -euo pipefail
test "$(id -u)" = 0
export DEBIAN_FRONTEND=noninteractive
apt-get install -y --no-install-recommends build-essential
root=/opt/loginom-swarm/toolchains
version=node-v24.19.0-linux-x64
test ! -e "$root/$version" || exit 0
stage=$(mktemp -d "$root/.node-XXXXXX")
curl -fsSL --retry 3 https://nodejs.org/dist/v24.19.0/SHASUMS256.txt -o "$stage/SHASUMS256.txt"
curl -fsSL --retry 3 "https://nodejs.org/dist/v24.19.0/$version.tar.xz" -o "$stage/$version.tar.xz"
(cd "$stage" && grep " $version.tar.xz$" SHASUMS256.txt | sha256sum -c -)
tar -xJf "$stage/$version.tar.xz" -C "$stage"
echo "bc17c508ffeed0ec622934f9b7fa72f8e78da65350e63c3eceb56fa688aa5e12  $stage/$version/bin/node" | sha256sum -c -
chown -R root:root "$stage/$version"
chmod -R go-w "$stage/$version"
mv "$stage/$version" "$root/$version"
install -d -m 755 /opt/loginom-swarm/runtime/bin
ln -s "$root/$version/bin/node" /opt/loginom-swarm/runtime/bin/node
ln -s "$root/20260925.1/bun-linux-x64/bun" /opt/loginom-swarm/runtime/bin/bun
ln -s "$root/$version/lib/node_modules/npm/node_modules/node-gyp/bin/node-gyp.js" /opt/loginom-swarm/runtime/bin/node-gyp
# Preserve the downloaded checksum list as build provenance; no credentials here.
mv "$stage/SHASUMS256.txt" "$root/$version/SHASUMS256.txt"
rm "$stage/$version.tar.xz"
rmdir "$stage"
