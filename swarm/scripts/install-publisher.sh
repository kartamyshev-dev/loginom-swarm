#!/bin/bash
# Run as root on the VPS. No model role receives this home or credential store.
set -euo pipefail
umask 077
id loginom-publisher >/dev/null 2>&1 || useradd --system --user-group --home-dir /var/lib/loginom-swarm-publisher --create-home --shell /usr/sbin/nologin loginom-publisher
home=/var/lib/loginom-swarm-publisher
install -d -m 0700 -o loginom-publisher -g loginom-publisher "$home" "$home/.config" "$home/.config/gh"
command -v gh >/dev/null
runuser -u loginom-publisher -- env -i HOME="$home" PATH=/usr/bin:/bin git config --global user.name kartamyshev-dev
runuser -u loginom-publisher -- env -i HOME="$home" PATH=/usr/bin:/bin git config --global user.email 97161574+kartamyshev-dev@users.noreply.github.com
runuser -u loginom-publisher -- env -i HOME="$home" PATH=/usr/bin:/bin git config --global credential.https://github.com.helper '!/usr/bin/gh auth git-credential'
echo 'Publisher account prepared; OAuth and publication verification are separate gates.'
