#!/bin/bash
set -euo pipefail

readonly REPO_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
readonly CAMERA_SOURCE="$REPO_ROOT/camera-admin"
readonly METADATA_SOURCE="$REPO_ROOT/metadata"

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  echo "Run this installer as root." >&2
  exit 1
fi

for required in \
  "$CAMERA_SOURCE/config/cameras.json" \
  "$METADATA_SOURCE/viltkamera-metadata-watch" \
  "$METADATA_SOURCE/viltkamera-metadata.service"; do
  if [[ ! -f "$required" ]]; then
    echo "Missing required file: $required" >&2
    if [[ "$required" == *cameras.json ]]; then
      echo "Copy cameras.example.json to cameras.json and enter private values." >&2
    fi
    exit 1
  fi
done

apt-get update
apt-get install -y --no-install-recommends \
  python3 libimage-exiftool-perl inotify-tools

install -o root -g root -m 0755 \
  "$METADATA_SOURCE/viltkamera-metadata-watch" \
  /usr/local/sbin/viltkamera-metadata-watch
install -o root -g root -m 0644 \
  "$METADATA_SOURCE/viltkamera-metadata.service" \
  /etc/systemd/system/viltkamera-metadata.service

bash "$CAMERA_SOURCE/install.sh" "$CAMERA_SOURCE"
systemctl daemon-reload
systemctl enable --now viltkamera-metadata.service

systemctl --no-pager --full status \
  viltkamera-metadata.service viltkamera-camera-admin.service || true
