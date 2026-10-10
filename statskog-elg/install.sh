#!/bin/bash
set -euo pipefail

source_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  printf 'Run this installer as root.\n' >&2
  exit 1
fi

command -v python3 >/dev/null 2>&1 || {
  printf 'python3 is required. Install it before continuing.\n' >&2
  exit 1
}

getent group statskog-elg >/dev/null 2>&1 || groupadd --system statskog-elg
getent group viltkamera-config >/dev/null 2>&1 || groupadd --system viltkamera-config
id statskog-elg >/dev/null 2>&1 || useradd \
  --system --gid statskog-elg --home-dir /var/lib/statskog-elg \
  --shell /usr/sbin/nologin statskog-elg
usermod --append --groups viltkamera-config statskog-elg

install -d -o root -g root -m 0755 /opt/statskog-elg
install -d -o root -g statskog-elg -m 0750 /etc/statskog-elg
install -d -o root -g viltkamera-config -m 2770 /etc/viltkamera-metadata
install -o root -g root -m 0755 "$source_dir/collector.py" \
  /opt/statskog-elg/collector.py

if [[ ! -e /etc/statskog-elg/statskog-elg.env ]]; then
  install -o root -g statskog-elg -m 0640 \
    "$source_dir/statskog-elg.env.example" \
    /etc/statskog-elg/statskog-elg.env
  printf 'Created /etc/statskog-elg/statskog-elg.env; add the Influx token.\n'
else
  printf 'Preserved existing /etc/statskog-elg/statskog-elg.env.\n'
fi

if [[ ! -e /etc/viltkamera-metadata/jaktfelt.json ]]; then
  install -o root -g viltkamera-config -m 0660 \
    "$source_dir/jaktfelt.example.json" \
    /etc/viltkamera-metadata/jaktfelt.json
  printf 'Created the web-editable hunting-ground configuration.\n'
else
  chgrp viltkamera-config /etc/viltkamera-metadata/jaktfelt.json
  chmod 0660 /etc/viltkamera-metadata/jaktfelt.json
  printf 'Preserved the existing hunting-ground configuration.\n'
fi

install -o root -g root -m 0644 "$source_dir/statskog-elg.service" \
  /etc/systemd/system/statskog-elg.service
install -o root -g root -m 0644 "$source_dir/statskog-elg.timer" \
  /etc/systemd/system/statskog-elg.timer
install -o root -g root -m 0644 "$source_dir/statskog-elg-config.path" \
  /etc/systemd/system/statskog-elg-config.path
systemctl daemon-reload
systemctl enable --now statskog-elg-config.path

cat <<'EOF'
Installation complete. Before enabling the timer:
  1. Edit /etc/statskog-elg/statskog-elg.env
  2. Test: sudo -u statskog-elg /opt/statskog-elg/collector.py --check-api
  3. Import once: systemctl start statskog-elg.service
  4. Inspect: journalctl -u statskog-elg.service -n 50 --no-pager
  5. Enable: systemctl enable --now statskog-elg.timer
EOF
