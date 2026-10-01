# Statskog elg collector

This component imports public Statskog ArcGIS harvest records for one hunting
field into an existing InfluxDB v2 bucket. The production defaults target:

- hunting field `1840J0096` / `Storjord Øst`
- species `Elg`
- InfluxDB organisation `Minsin`
- bucket `Wildlife`
- measurement `elg_felling`

It does not request or store ArcGIS geometry. A Statskog map point must not be
presented as the exact kill location.

## Data behaviour

The collector queries `Storvilt skutt` (layer 0), follows ArcGIS pagination and
deduplicates source rows by `StorviltID`. If a source ID is missing, it falls
back to `GlobalID`, then `OBJECTID`.

The local state file stores a SHA-256 fingerprint per event. Unchanged events
are not sent again during every poll. If the state file is lost, rewriting the
same data remains safe because measurement, stable tags and source timestamp
produce the same Influx point identity.

The source currently contains one duplicate logical event and one zero weight
for this hunting field. Duplicate revisions are collapsed. Zero, negative and
unparseable weights are retained as `slaktevekt_raw` with
`slaktevekt_gyldig=false`, but no numeric `slaktevekt` field is written. They
therefore do not skew averages.

`Kategori` and the more detailed `Kategoriskutt` are stored as string fields
named `kategori` and `kategori_skutt`. They are deliberately not tags: a source
correction then updates the existing point instead of creating another series.

The collector also resolves the field's public numeric ID and reads only the
start/end dates from the public hunting-period layer. Periods are labelled by
start date as `Jaktlag 1`, `Jaktlag 2`, and `Andre`; leader names and phone
numbers are neither requested nor stored. Event dates are matched in
`Europe/Oslo`, including both the first and last day of each period.

## Install on the host that can reach InfluxDB

```bash
cd /path/to/wildlife-camera-gallery-stack/statskog-elg
sudo ./install.sh
sudoedit /etc/statskog-elg/statskog-elg.env
```

Create a dedicated InfluxDB v2 API token with write access to the `Wildlife`
bucket and place it in `INFLUX_TOKEN`. Do not put the configured environment
file in Git.

Verify the public source without needing Influx credentials:

```bash
sudo -u statskog-elg /opt/statskog-elg/collector.py --check-api
```

Run the initial historical import and inspect it:

```bash
sudo systemctl start statskog-elg.service
sudo journalctl -u statskog-elg.service -n 50 --no-pager
```

Then enable polling every ten minutes:

```bash
sudo systemctl enable --now statskog-elg.timer
systemctl list-timers statskog-elg.timer
```

## Manual modes

```bash
# Produce line protocol without writing or updating state
sudo -u statskog-elg /opt/statskog-elg/collector.py --dry-run

# Re-send every current source event using the same idempotent point identity
sudo -u statskog-elg /opt/statskog-elg/collector.py --force
```

Statskog source deletions are not automatically deleted from InfluxDB. This is
intentional: the polling job never performs destructive database operations.
Investigate and remove a withdrawn event manually if Statskog deletes one.

## Stored schema

Stable tags:

- `art`
- `jaktfelt`
- `jaktfelt_id`
- `storvilt_id`

Fields include:

- `felling=1`
- `kategori` (string)
- `kategori_skutt` (string)
- `jaktlag` (`Jaktlag 1`, `Jaktlag 2`, or `Andre`)
- `jaktperiode_start` and `jaktperiode_slutt` (ISO dates when matched)
- `slaktevekt` (float, only for positive parsed values)
- `slaktevekt_raw` (string)
- `slaktevekt_gyldig` (boolean)
- `kontrollert_vekt` (float when available)
- source audit identifiers and timestamps

The Influx timestamp is Statskog's `Dato` value. Grafana should display it in
`Europe/Oslo`.

## Grafana

The Norwegian dashboard JSON includes an **Elgjakt – Storjord Øst** section.
Standalone Flux queries are also under [`flux/`](flux/) for inspection and
reuse. Quota and remaining quota are not included because the verified ArcGIS
layers do not expose a stable quota field.

## Tests

```bash
python3 -m unittest discover -s tests -v
```
