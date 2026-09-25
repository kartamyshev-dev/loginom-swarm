#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/../.."
image=${1:?Usage: build-image.sh ghcr.io/kartamyshev-dev/loginom-swarm:VERSION}
[[ "$image" =~ ^ghcr.io/kartamyshev-dev/loginom-swarm:[A-Za-z0-9._-]+$ ]] || exit 2
test -z "$(git status --porcelain --untracked-files=normal)" || { echo 'Commit the reviewed source before building.' >&2; exit 1; }
python3 swarm/scripts/check-upstream.py
commit=$(git rev-parse HEAD)
upstream=$(python3 -c 'import json; print(json.load(open("swarm/upstream.lock.json"))["tag"])')
base="loginom-swarm-source:$commit"
docker build --platform linux/amd64 --target production \
  --build-arg CLI_PACKAGES=@openai/codex@0.155.1 \
  --build-arg PAPERCLIP_BUILD_COMMIT="$commit" \
  --build-arg PAPERCLIP_BUILD_VERSION="${image##*:}" \
  --label "org.opencontainers.image.revision=$commit" -t "$base" .
test "$(docker image inspect "$base" --format '{{index .Config.Labels "org.opencontainers.image.revision"}}')" = "$commit"
docker build --platform linux/amd64 -f swarm/deploy/Dockerfile \
  --build-arg PAPERCLIP_SOURCE_IMAGE="$base" --build-arg SWARM_COMMIT="$commit" \
  --build-arg SWARM_VERSION="${image##*:}" --build-arg UPSTREAM_VERSION="$upstream" -t "$image" .
docker image inspect "$image" --format '{{.Id}}'
# Publishing and deployment are separate explicit operations.
