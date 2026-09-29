# Wildlife video validator

Some Suntek HC960Ultra cameras occasionally produce MP4 files without a valid
`moov` atom during heavy trigger bursts. The same broken files are present in
the manufacturer's app, so this is camera-side corruption rather than damage
introduced by SFTPGo or PiGallery2.

The live service waits five seconds after a completed upload, runs `ffprobe`,
and retries three times with 15 seconds between attempts. A file that still
fails is moved to the matching folder below `/srv/sftpgo/quarantine`. That
directory must remain outside `/srv/sftpgo/data`, otherwise PiGallery will see
and repeatedly attempt to thumbnail the broken video.

The timer also scans all existing MP4 files every six hours. The validator is
separate from `wildlife-ocr.service`, so video failures cannot interrupt JPEG
OCR or Uptime Kuma heartbeats.

## Install

The captured deployment reuses `/opt/wildlife-ocr/venv`. Install the OCR
environment first, then run:

```bash
sudo ./wildlife-video-validator/install.sh
sudo systemctl start wildlife-video-scan.service
```

The first scan can take a while and may move files. Inspect its log before
restarting PiGallery:

```bash
journalctl -u wildlife-video-scan.service --no-pager
find /srv/sftpgo/quarantine -type f -printf '%P\n'
cd /opt/pigallery2 && docker compose restart
```

## Operations

```bash
systemctl status wildlife-video-validator.service
systemctl list-timers wildlife-video-scan.timer
journalctl -u wildlife-video-validator -f
journalctl -u wildlife-video-scan.service

# Manual full scan, equivalent to the oneshot unit
sudo -u sftpgo \
  /opt/wildlife-ocr/venv/bin/python \
  /opt/wildlife-video-validator/video_validator.py --scan
```

Typical log messages are `VALID`, three `INVALID attempt=N/3` messages, and
then `QUARANTINED`. The scanner logs `Existing scan complete total=N broken=N`.

## Future hardening

The current upload directory is also PiGallery's source tree, so PiGallery can
briefly see a partial or corrupt upload before validation finishes. A future
staging design should receive files outside the gallery tree, validate them,
and atomically move only valid MP4 files into `/srv/sftpgo/data/hc960-NN/`.
