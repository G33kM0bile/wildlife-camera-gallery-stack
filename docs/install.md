# Installation and recreation guide

This guide mirrors the captured two-container layout. Commands assume root on
Debian 13. Adjust addresses and mount technology for your environment.

## 1. Prepare storage

Create the writable photo tree on the SFTPGo host:

```bash
install -d -o sftpgo -g sftpgo -m 0750 /srv/sftpgo/data
for n in 01 02 03 04 05; do
  install -d -o sftpgo -g sftpgo -m 0750 "/srv/sftpgo/data/hc960-$n"
done
```

Create the video quarantine as a sibling of `data`, never below it:

```bash
install -d -o sftpgo -g sftpgo -m 0750 /srv/sftpgo/quarantine
for n in 01 02 03 04 05; do
  install -d -o sftpgo -g sftpgo -m 0750 \
    "/srv/sftpgo/quarantine/hc960-$n"
done
```

Expose that tree to the PiGallery host using a storage mount appropriate for
the lab (bind mount, NFS, CephFS, Proxmox mount point, etc.). Mount it read-only
at `/photos` on the PiGallery host. Verify with:

```bash
findmnt /photos
touch /photos/.write-test   # this must fail on the PiGallery host
```

## 2. Install and configure SFTPGo

Use the official SFTPGo package or `compose/sftpgo/compose.yaml`. The captured
deployment ran SFTPGo 2.7.5 as a native systemd service and kept its photo root
at `/srv/sftpgo/data`.

In WebAdmin:

1. Replace the initial administrator credentials.
2. Create one user per camera.
3. Give each user a home/folder that resolves only to its own `hc960-NN`
   directory.
4. Disable protocols and permissions the cameras do not use.
5. Test upload, rename and reconnect from every camera.
6. Keep WebAdmin bound to a trusted interface or reverse-proxy it with strong
   access controls.

Do not export SFTPGo users into Git: exports can include password hashes,
public keys and private filesystem information.

## 3. Install metadata automation and camera admin

Copy this repository to the SFTPGo host, edit
`camera-admin/config/cameras.example.json` with private real data, and save it
as `camera-admin/config/cameras.json` (ignored by Git).

Then run:

```bash
sudo ./scripts/install-metadata-stack.sh
```

The installer adds `python3`, `libimage-exiftool-perl` and `inotify-tools`,
installs the two services, and preserves an existing production
`cameras.json`. Inspect status:

```bash
systemctl status viltkamera-metadata viltkamera-camera-admin
journalctl -u viltkamera-metadata -f
```

The admin UI defaults to `127.0.0.1:9095`. Change its systemd environment only
if a trusted LAN or reverse proxy must reach it, then run `systemctl
daemon-reload` and restart the service.

## 4. Install MP4 validation

The video validator requires the existing wildlife OCR virtual environment and
installs `ffprobe` plus `watchdog`:

```bash
sudo ./wildlife-video-validator/install.sh
sudo systemctl start wildlife-video-scan.service
sudo journalctl -u wildlife-video-scan.service --no-pager
```

Confirm that invalid files, if any, moved to `/srv/sftpgo/quarantine`, then
optionally add the status block to the existing system MOTD:

```bash
sudo ./motd/install.sh
```

See `wildlife-video-validator/README.md` before changing paths or retry timing.

## 5. Deploy PiGallery2

```bash
install -d -m 0750 /opt/pigallery2/{config,db,tmp}
cd /path/to/repository/compose/pigallery2
cp ../../.env.example .env
# Edit PIGALLERY_BIND, PIGALLERY_PORT, PHOTO_ROOT and PIGALLERY_ROOT.
docker compose --env-file .env up -d
docker compose ps
```

Open PiGallery2, immediately replace the initial admin password, enable the
database/indexing settings appropriate for the library, and run the first
index. PiGallery2 should see `/app/data/images` inside the container; do not
change that internal path in the UI.

## 6. Install verified sightings

```bash
install -d -m 0750 \
  /opt/pigallery2/config/extensions/verified-sightings
cp extensions/verified-sightings/package.json \
   extensions/verified-sightings/server.js \
   /opt/pigallery2/config/extensions/verified-sightings/
cd /opt/pigallery2
docker compose restart
```

Enable the extension in PiGallery2 Settings if it is not discovered
automatically. After marking one photo, confirm the writable registry exists:

```text
/opt/pigallery2/config/extensions/verified-sightings/verified-sightings.json
```

## 7. Build the GPX waypoint image (optional)

The overlay is version-specific and currently targets 3.5.2:

```bash
cd pigallery2-map
./build.sh
```

Set `PIGALLERY_IMAGE=viltkamera/pigallery2:3.5.2-map-waypoints` in the PiGallery
`.env`, then recreate the container. See [maps-and-gpx.md](maps-and-gpx.md).

## 8. Add a private GPX map

Copy `gpx/example.gpx` outside the repository, replace every fake coordinate,
and place the production file at the top of the photo tree. Include `name`,
`desc`, `sym` and `type` for useful popups and deterministic colors.

## 9. Reverse proxy and DNS

Terminate TLS at the preferred reverse proxy and proxy only PiGallery's HTTP
port. Preserve normal forwarding headers and WebSocket support. Do not bypass
PiGallery authentication just because the URL is public.

## 10. QR-code information page

Keep the existing public URL stable because it is encoded in labels attached
to the physical cameras:

```bash
install -o root -g root -m 0644 \
  information-site/viltkamera.html /var/www/html/viltkamera.html
```

Restore `/var/www/html/grunneiertillatelse.jpg` from protected backup. It is
not stored in Git. See `information-site/README.md`.

## 11. Grafana (optional)

Import `grafana/viltkamera-grafana-dashboard-no.json`, choose the InfluxDB 2.x
Flux datasource when prompted, and verify the default 48-hour range. The
dashboard contains no datasource UID or credentials.

## 12. Statskog elg collector (optional)

Install this on a host that can reach both Statskog over HTTPS and InfluxDB:

```bash
cd /path/to/repository/statskog-elg
sudo ./install.sh
sudoedit /etc/statskog-elg/statskog-elg.env
sudo -u statskog-elg /opt/statskog-elg/collector.py --check-api
sudo systemctl start statskog-elg.service
sudo journalctl -u statskog-elg.service -n 50 --no-pager
sudo systemctl enable --now statskog-elg.timer
```

Use a dedicated token with write access only to `Wildlife`. The first run
imports the available history; later runs send only new or changed records.
See `statskog-elg/README.md` for schema and recovery behaviour.

## 13. Acceptance test

Run `scripts/validate-deployment.sh` locally on each relevant host, then test:

1. a camera can upload a new JPEG;
2. ExifTool shows expected title, subject, comment, tags and GPS;
3. PiGallery discovers the new image;
4. a normal logged-in user can mark/unmark a verified sighting;
5. the map shows named/color-coded GPX pins and tracks;
6. the photo tree remains read-only from the PiGallery host;
7. backups can be restored into a disposable instance.
8. `https://8370.no/viltkamera.html?id=hc960-01` retains its public URL and
   displays the selected camera ID.
9. `statskog-elg.timer` is active and a second manual collector run reports no
   new or changed felling records.
10. `wildlife-video-validator.service` is active, the six-hour timer is
    enabled, and a full scan reports no broken MP4 remaining below
    `/srv/sftpgo/data`.
