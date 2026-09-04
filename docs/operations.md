# Operations, backup and recovery

## Routine checks

```bash
systemctl is-active sftpgo viltkamera-metadata viltkamera-camera-admin
journalctl -u viltkamera-metadata --since today
cd /opt/pigallery2 && docker compose ps
cd /opt/pigallery2 && docker compose logs --tail=100
findmnt /photos
```

Check free space on the photo store, SFTPGo state and PiGallery database/tmp
volumes. A full photo filesystem can break uploads and SQLite writes in
different ways.

## Configuration-only backup

On a host where the paths are present:

```bash
sudo ./scripts/backup-state.sh /srv/backups/wildlife-camera
```

This captures configuration, SQLite databases, extension state and service
definitions. It intentionally excludes the photo library. Protect the archive
because it may contain usernames, password hashes and private coordinates.

Use filesystem/storage snapshots or a separate versioned backup job for the
photo tree. Test both backups together.

## Restore order

1. Build fresh Debian hosts/containers and restore the photo filesystem.
2. Restore SFTPGo provider/config state with SFTPGo stopped.
3. Restore `/etc/viltkamera-metadata` and reinstall the service definitions.
4. Restore PiGallery `config/` and `db/` with its container stopped.
5. Restore the verified-sightings registry (normally already inside config).
6. Restore the Caddy configuration, `viltkamera.html`, and the protected
   `grunneiertillatelse.jpg` without changing the QR-code URL.
7. Recreate mounts, starting SFTPGo before the metadata watcher and PiGallery.
8. Confirm PiGallery's photo mount is read-only.
9. Validate logins, one upload, metadata, the map and a verified sighting.

Never restore only PiGallery's SQLite database while pairing it with a
different config or photo-tree layout without first testing in a disposable
instance.

## Upgrades

Before changing SFTPGo or PiGallery2:

1. take Proxmox/storage snapshots;
2. run the state backup;
3. record current image digests and package versions;
4. read upstream release notes for migrations;
5. test the extension and map overlay against the new PiGallery version;
6. upgrade one component at a time;
7. retain the previous Compose file/image until acceptance tests pass.

The PiGallery map overlay modifies upstream frontend source, so assume it needs
review for every PiGallery upgrade. The verified-sightings extension depends on
`pigallery2-extension-kit` 3.5.2 and must also be rebuilt/tested.

## Rollback for the custom map image

Change `PIGALLERY_IMAGE` back to the previously recorded image and recreate:

```bash
cd /opt/pigallery2
docker compose up -d --force-recreate
```

The map image does not modify PiGallery config, database or photos. GPX files
should be backed up separately before replacement.
