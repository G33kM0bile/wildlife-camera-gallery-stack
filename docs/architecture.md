# Architecture and data flow

## Components

### SFTPGo host

SFTPGo is the only component that accepts writes from cameras. The reference
root is `/srv/sftpgo/data`, with one folder per device:

```text
/srv/sftpgo/data/
├── hc960-01/
├── hc960-02/
├── hc960-03/
├── hc960-04/
├── hc960-05/
└── private-map.gpx
```

Restrict every SFTP account to its matching folder. Do not give cameras access
to sibling folders or the SFTPGo administration interface.

The inotify watcher calls the metadata handler only after `close_write` or
`moved_to`. The handler resolves and validates the path, accepts JPEG files
only, maps the first relative path component to a configured camera, compares
existing metadata, and uses ExifTool only when a change is required.

### Camera admin UI

The UI is intentionally small and has no independent account database. A login
is checked against the SFTPGo `/api/v2/token` endpoint. The password is not
stored. Successful sessions are memory-only, HttpOnly, SameSite=Strict cookies
with CSRF tokens.

Configuration changes are validated, written atomically and retained in a
short history directory. They affect future uploads only.

### PiGallery2 host

The same photo tree is mounted at `/photos`, then mounted read-only into the
container as `/app/data/images`. PiGallery's mutable config, SQLite databases
and temporary files live separately below `/opt/pigallery2`.

The verified-sightings extension stores the authoritative list of marked image
paths in its own `verified-sightings.json`. It reapplies a keyword during
metadata loading so a re-index does not erase album membership.

The GPX map overlay changes only the web frontend. It preserves PiGallery's GPX
tracks and adds waypoint metadata parsing, escaped popups and category colors.

### Grafana/InfluxDB

This is optional and independent of the gallery. The included dashboard expects:

- bucket `Wildlife`
- measurement `wildlife_camera`
- tag `camera`
- fields `image`, `ocr_ok`, `temperature_c`, `temperature_f`, `battery_pct`
- cameras `hc960-01` through `hc960-05`

Datasource credentials stay in Grafana and are not embedded in the dashboard.
The live OCR watcher validates the printed Celsius/Fahrenheit pair before it
writes temperature fields. The dashboard also limits displayed temperature to
-40–40 °C so old OCR spikes remain stored but do not distort the graphs.

### Statskog harvest collector

The optional `statskog-elg` oneshot service polls Statskog's public ArcGIS
layer for `Art='Elg'` and `JaktfeltID='1840J0096'`. A systemd timer runs it
every ten minutes. It deduplicates source revisions by `StorviltID`, records
source `Dato` as the Influx timestamp and writes measurement `elg_felling` to
the existing `Wildlife` bucket.

The collector keeps fingerprints in `/var/lib/statskog-elg/state.json`, so
unchanged events are not transmitted repeatedly. It never requests geometry
and does not represent ArcGIS points as exact kill locations.

## Trust boundaries

- Internet -> reverse proxy -> PiGallery2: authenticated gallery access.
- Camera network -> SFTPGo SFTP port: upload-only device accounts.
- Trusted admin network -> SFTPGo WebAdmin and camera admin UI.
- PiGallery2 -> photo storage: read-only.
- Metadata service -> photo storage: narrowly scoped write access.
- Elg collector -> Statskog: public read-only HTTPS queries.
- Elg collector -> InfluxDB: token restricted to bucket write access.

Do not expose SFTPGo WebAdmin or camera-admin directly to the public internet.
