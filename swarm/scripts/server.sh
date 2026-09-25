#!/bin/sh
set -eu
project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
. "$project_dir/.env"
export SSHPASS="$SERVER_PASSWORD"
exec sshpass -e ssh -o StrictHostKeyChecking=accept-new -o ConnectTimeout=15 \
  -o NumberOfPasswordPrompts=1 -o ServerAliveInterval=20 -o ServerAliveCountMax=3 \
  -p "$SERVER_PORT" "$SERVER_USER@$SERVER_HOST" "$@"
