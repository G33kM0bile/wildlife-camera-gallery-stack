#!/bin/bash
set -u

hostname
command -v sftpgo || true
sftpgo --version 2>/dev/null | head -n 2 || true
command -v exiftool || true
command -v inotifywait || true
systemctl is-active sftpgo 2>/dev/null || true
systemctl show -p FragmentPath -p EnvironmentFiles sftpgo 2>/dev/null || true
id sftpgo 2>/dev/null || true
stat -c '%A %U:%G %n' /srv/sftpgo /srv/sftpgo/data /srv/sftpgo/data/hc960-01
find /etc /opt -maxdepth 3 -type f \( -iname '*sftpgo*.json' -o -iname 'sftpgo*.yaml' \) -print 2>/dev/null
find /srv/sftpgo/data -maxdepth 2 -type f \( -iname '*.jpg' -o -iname '*.jpeg' \) -printf '%h\n' | sort | uniq -c
