#!/bin/bash
set -u

status=0
check() {
  local label=$1
  shift
  if "$@" >/dev/null 2>&1; then
    printf 'OK   %s\n' "$label"
  else
    printf 'FAIL %s\n' "$label"
    status=1
  fi
}

command -v systemctl >/dev/null 2>&1 && {
  systemctl list-unit-files sftpgo.service >/dev/null 2>&1 && \
    check "SFTPGo service" systemctl is-active --quiet sftpgo
  systemctl list-unit-files viltkamera-metadata.service >/dev/null 2>&1 && \
    check "metadata watcher" systemctl is-active --quiet viltkamera-metadata
  systemctl list-unit-files viltkamera-camera-admin.service >/dev/null 2>&1 && \
    check "camera admin" systemctl is-active --quiet viltkamera-camera-admin
  systemctl list-unit-files statskog-elg.timer >/dev/null 2>&1 && \
    check "Statskog elg timer" systemctl is-active --quiet statskog-elg.timer
}

[[ -d /srv/sftpgo/data ]] && check "SFTPGo photo root" test -d /srv/sftpgo/data
[[ -d /photos ]] && check "PiGallery photo mount" mountpoint -q /photos

if command -v docker >/dev/null 2>&1 && [[ -f /opt/pigallery2/compose.yaml ]]; then
  check "PiGallery Compose config" \
    sh -c 'cd /opt/pigallery2 && docker compose config -q'
  check "PiGallery container" \
    sh -c 'cd /opt/pigallery2 && docker compose ps --status running --quiet | grep -q .'
fi

exit "$status"
