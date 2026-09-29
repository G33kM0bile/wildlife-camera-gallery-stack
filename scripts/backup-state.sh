#!/bin/bash
set -euo pipefail

readonly DESTINATION=${1:-}
if [[ -z "$DESTINATION" ]]; then
  echo "Usage: $0 /secure/backup/directory" >&2
  exit 64
fi
if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  echo "Run as root so protected state can be read." >&2
  exit 1
fi

install -d -o root -g root -m 0700 "$DESTINATION"
readonly STAMP=$(date -u +%Y%m%dT%H%M%SZ)
readonly ARCHIVE="$DESTINATION/wildlife-camera-state-$STAMP.tar.gz"

declare -a PATHS=()
for candidate in \
  /etc/sftpgo \
  /var/lib/sftpgo \
  /etc/viltkamera-metadata \
  /etc/statskog-elg \
  /var/lib/statskog-elg \
  /etc/systemd/system/statskog-elg.service \
  /etc/systemd/system/statskog-elg.timer \
  /etc/systemd/system/wildlife-video-validator.service \
  /etc/systemd/system/wildlife-video-scan.service \
  /etc/systemd/system/wildlife-video-scan.timer \
  /etc/update-motd.d/99-wildlife-camera \
  /opt/wildlife-video-validator \
  /etc/systemd/system/viltkamera-metadata.service \
  /etc/systemd/system/viltkamera-camera-admin.service \
  /opt/viltkamera-camera-admin \
  /opt/pigallery2/config \
  /opt/pigallery2/db \
  /opt/pigallery2/compose.yaml; do
  [[ -e "$candidate" ]] && PATHS+=("${candidate#/}")
done

if [[ ${#PATHS[@]} -eq 0 ]]; then
  echo "No known state paths were found on this host." >&2
  exit 1
fi

tar -C / -czf "$ARCHIVE" "${PATHS[@]}"
chmod 0600 "$ARCHIVE"
sha256sum "$ARCHIVE" > "$ARCHIVE.sha256"
chmod 0600 "$ARCHIVE.sha256"
echo "$ARCHIVE"
echo "Photo files are not included; back them up separately."
