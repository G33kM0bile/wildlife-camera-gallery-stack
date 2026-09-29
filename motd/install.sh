#!/bin/bash
set -euo pipefail

source_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  printf 'Run this installer as root.\n' >&2
  exit 1
fi

install -o root -g root -m 0755 "$source_dir/99-wildlife-camera" \
  /etc/update-motd.d/99-wildlife-camera

printf 'Installed /etc/update-motd.d/99-wildlife-camera\n'
/etc/update-motd.d/99-wildlife-camera
