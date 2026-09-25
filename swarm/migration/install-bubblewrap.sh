#!/bin/bash
# Ubuntu 26.04 amd64 only. Keep the distro /usr/bin/bwrap policy unchanged.
set -euo pipefail
[[ $EUID == 0 && $(dpkg --print-architecture) == amd64 ]]
[[ $(dpkg-query -W -f='${Version}' bubblewrap) == 0.11.1-1ubuntu0.3 ]]
expected=523da3e7399044be5163aee6f57a77a6bef7454376e28f0a0627920bae1b76b6
[[ $(sha256sum /usr/bin/bwrap | cut -d ' ' -f 1) == "$expected" ]]
[[ $(stat -c '%u:%g:%a' /usr/bin/bwrap) == 0:0:755 ]]
install -d -o root -g root -m 0755 /usr/local/libexec/loginom-swarm
install -o root -g root -m 0755 /usr/bin/bwrap /usr/local/libexec/loginom-swarm/bwrap
[[ $(sha256sum /usr/local/libexec/loginom-swarm/bwrap | cut -d ' ' -f 1) == "$expected" ]]
echo 'Qualified Bubblewrap installed. AppArmor and namespace isolation remain required.'
