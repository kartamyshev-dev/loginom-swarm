#!/bin/bash
# Run as root on the VPS, in a durable session. Never use gh auth token in logs.
set -euo pipefail
umask 077
exec runuser -u loginom-publisher -- env -i \
  HOME=/var/lib/loginom-swarm-publisher PATH=/usr/bin:/bin \
  GH_CONFIG_DIR=/var/lib/loginom-swarm-publisher/.config/gh BROWSER=/usr/bin/true \
  gh auth login --hostname github.com --git-protocol https --web
