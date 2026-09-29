#!/bin/bash
set -euo pipefail

source_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
python_bin=/opt/wildlife-ocr/venv/bin/python

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  printf 'Run this installer as root.\n' >&2
  exit 1
fi
if ! id sftpgo >/dev/null 2>&1; then
  printf 'The sftpgo service account is required.\n' >&2
  exit 1
fi
if [[ ! -x "$python_bin" ]]; then
  printf 'Missing %s; install the existing wildlife OCR environment first.\n' \
    "$python_bin" >&2
  exit 1
fi

apt-get update
apt-get install -y --no-install-recommends ffmpeg
"$python_bin" -m pip install 'watchdog>=4,<7'

install -d -o root -g root -m 0755 /opt/wildlife-video-validator
install -o root -g root -m 0755 "$source_dir/video_validator.py" \
  /opt/wildlife-video-validator/video_validator.py

install -d -o sftpgo -g sftpgo -m 0750 /srv/sftpgo/quarantine
for number in 01 02 03 04 05; do
  install -d -o sftpgo -g sftpgo -m 0750 \
    "/srv/sftpgo/quarantine/hc960-$number"
done

for unit in \
  wildlife-video-validator.service \
  wildlife-video-scan.service \
  wildlife-video-scan.timer; do
  install -o root -g root -m 0644 "$source_dir/$unit" "/etc/systemd/system/$unit"
done

systemctl daemon-reload
systemctl enable --now wildlife-video-validator.service
systemctl enable --now wildlife-video-scan.timer

printf '%s\n' \
  'Video validation installed.' \
  'Run a full check with: systemctl start wildlife-video-scan.service' \
  'Follow uploads with: journalctl -u wildlife-video-validator -f'
