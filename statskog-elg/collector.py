#!/usr/bin/env python3
"""Collect moose harvest events from Statskog ArcGIS and write InfluxDB v2."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo


LOG = logging.getLogger("statskog-elg")
DEFAULT_ARCGIS_URL = (
    "https://kartportal.statskog.no/server/rest/services/"
    "Storvilt_2024/Storvilt_app_innsyn/MapServer"
)
MEASUREMENT = "elg_felling"
SOURCE_FIELDS = (
    "Art,Kategori,Kategoriskutt,Dato,Dato_Tekst,Slaktevekt,"
    "Kontrollert_vekt,JaktfeltID,StorviltID,HjorteviltID,GlobalID,"
    "OBJECTID,created_date,last_edited_date"
)
JAKTFELT_LOOKUP_FIELDS = "JaktfeltUnikID"
JAKTLAG_PERIOD_FIELDS = "Jaktstart,Jaktslutt,JaktfeltUnikID"


class CollectorError(RuntimeError):
    """Expected collector failure with a user-readable message."""


@dataclass(frozen=True)
class Config:
    arcgis_url: str
    arcgis_layer: int
    jaktfelt_lookup_layer: int
    jaktlag_period_layer: int
    jaktfelt_id: str
    jaktfelt_name: str
    art: str
    influx_url: str
    influx_token: str
    influx_org: str
    influx_bucket: str
    state_file: Path
    timeout_seconds: int
    page_size: int
    batch_size: int
    local_timezone: str

    @classmethod
    def from_env(cls, require_influx: bool = True) -> "Config":
        def env(name: str, default: str = "") -> str:
            return os.environ.get(name, default).strip()

        influx_url = env("INFLUX_URL")
        influx_token = env("INFLUX_TOKEN")
        missing = []
        if require_influx and not influx_url:
            missing.append("INFLUX_URL")
        if require_influx and not influx_token:
            missing.append("INFLUX_TOKEN")
        if missing:
            raise CollectorError(
                "Mangler påkrevd konfigurasjon: " + ", ".join(missing)
            )

        config = cls(
            arcgis_url=env("STATSKOG_ARCGIS_URL", DEFAULT_ARCGIS_URL).rstrip("/"),
            arcgis_layer=int(env("STATSKOG_LAYER", "0")),
            jaktfelt_lookup_layer=int(env("STATSKOG_JAKTFELT_LAYER", "4")),
            jaktlag_period_layer=int(env("STATSKOG_JAKTLAG_LAYER", "8")),
            jaktfelt_id=env("JAKTFELT_ID", "1840J0096"),
            jaktfelt_name=env("JAKTFELT_NAME", "Storjord Øst"),
            art=env("ART", "Elg"),
            influx_url=influx_url.rstrip("/"),
            influx_token=influx_token,
            influx_org=env("INFLUX_ORG", "Minsin"),
            influx_bucket=env("INFLUX_BUCKET", "Wildlife"),
            state_file=Path(
                env("STATE_FILE", "/var/lib/statskog-elg/state.json")
            ),
            timeout_seconds=int(env("HTTP_TIMEOUT_SECONDS", "30")),
            page_size=int(env("ARCGIS_PAGE_SIZE", "1000")),
            batch_size=int(env("INFLUX_BATCH_SIZE", "500")),
            local_timezone=env("LOCAL_TIMEZONE", "Europe/Oslo"),
        )
        if not config.jaktfelt_id or not config.art:
            raise CollectorError("JAKTFELT_ID og ART kan ikke være tomme")
        if config.timeout_seconds < 1 or config.page_size < 1 or config.batch_size < 1:
            raise CollectorError("Timeout, sidestørrelse og batchstørrelse må være positive")
        _require_http_url(config.arcgis_url, "STATSKOG_ARCGIS_URL")
        try:
            ZoneInfo(config.local_timezone)
        except (KeyError, ValueError) as exc:
            raise CollectorError("LOCAL_TIMEZONE må være en gyldig IANA-tidssone") from exc
        if require_influx:
            _require_http_url(config.influx_url, "INFLUX_URL")
        return config


def _require_http_url(value: str, name: str) -> None:
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise CollectorError(f"{name} må være en gyldig http(s)-URL")


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _json_request(url: str, timeout: int) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "statskog-elg-collector/1.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.load(response)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise CollectorError(f"Kunne ikke hente ArcGIS-data: {exc}") from exc
    if not isinstance(payload, dict):
        raise CollectorError("ArcGIS returnerte et uventet svar")
    if "error" in payload:
        error = payload["error"]
        raise CollectorError(f"ArcGIS-feil: {error}")
    return payload


def fetch_events(config: Config) -> list[dict[str, Any]]:
    """Fetch every matching row, following ArcGIS result pagination."""
    where = (
        f"Art = {_sql_literal(config.art)} AND "
        f"JaktfeltID = {_sql_literal(config.jaktfelt_id)}"
    )
    endpoint = f"{config.arcgis_url}/{config.arcgis_layer}/query"
    offset = 0
    rows: list[dict[str, Any]] = []

    while True:
        params = {
            "f": "json",
            "where": where,
            "outFields": SOURCE_FIELDS,
            "returnGeometry": "false",
            "orderByFields": "OBJECTID ASC",
            "resultOffset": str(offset),
            "resultRecordCount": str(config.page_size),
        }
        payload = _json_request(
            endpoint + "?" + urllib.parse.urlencode(params), config.timeout_seconds
        )
        features = payload.get("features", [])
        if not isinstance(features, list):
            raise CollectorError("ArcGIS-svaret mangler en gyldig features-liste")
        page = []
        for feature in features:
            attributes = feature.get("attributes") if isinstance(feature, dict) else None
            if isinstance(attributes, dict):
                page.append(attributes)
        rows.extend(page)
        offset += len(features)
        if not payload.get("exceededTransferLimit") and len(features) < config.page_size:
            break
        if not features:
            break

    return rows


@dataclass(frozen=True)
class HuntingPeriod:
    start: date
    end: date
    label: str


def _query_features(
    config: Config,
    layer: int,
    where: str,
    out_fields: str,
    order_by: str = "",
) -> list[dict[str, Any]]:
    params = {
        "f": "json",
        "where": where,
        "outFields": out_fields,
        "returnGeometry": "false",
    }
    if order_by:
        params["orderByFields"] = order_by
    endpoint = f"{config.arcgis_url}/{layer}/query"
    payload = _json_request(
        endpoint + "?" + urllib.parse.urlencode(params), config.timeout_seconds
    )
    features = payload.get("features", [])
    if not isinstance(features, list):
        raise CollectorError("ArcGIS-svaret mangler en gyldig features-liste")
    return [
        feature["attributes"]
        for feature in features
        if isinstance(feature, dict) and isinstance(feature.get("attributes"), dict)
    ]


def fetch_jaktfelt_unik_id(config: Config) -> int:
    """Resolve the public field ID without requesting leader/contact details."""
    rows = _query_features(
        config,
        config.jaktfelt_lookup_layer,
        f"JaktfeltID = {_sql_literal(config.jaktfelt_id)}",
        JAKTFELT_LOOKUP_FIELDS,
    )
    values = {
        value
        for row in rows
        if (value := _as_int(row.get("JaktfeltUnikID"))) is not None
    }
    if len(values) != 1:
        raise CollectorError(
            f"Forventet ett JaktfeltUnikID for {config.jaktfelt_id}, fant {len(values)}"
        )
    return values.pop()


def _local_date(timestamp_ms: Any, timezone_name: str) -> date | None:
    value = _as_int(timestamp_ms)
    if value is None or value <= 0:
        return None
    return datetime.fromtimestamp(
        value / 1000, tz=timezone.utc
    ).astimezone(ZoneInfo(timezone_name)).date()


def fetch_hunting_periods(
    config: Config, jaktfelt_unik_id: int, years: Iterable[int]
) -> list[HuntingPeriod]:
    """Fetch only period boundaries and assign privacy-safe labels by start date."""
    periods: list[HuntingPeriod] = []
    for year in sorted(set(years)):
        where = (
            f"JaktfeltUnikID = {jaktfelt_unik_id} AND "
            f"Jaktstart >= DATE '{year}-01-01' AND "
            f"Jaktstart < DATE '{year + 1}-01-01'"
        )
        rows = _query_features(
            config,
            config.jaktlag_period_layer,
            where,
            JAKTLAG_PERIOD_FIELDS,
            "Jaktstart ASC",
        )
        valid: list[tuple[date, date]] = []
        for row in rows:
            start = _local_date(row.get("Jaktstart"), config.local_timezone)
            end = _local_date(row.get("Jaktslutt"), config.local_timezone)
            if start is not None and end is not None and start <= end:
                valid.append((start, end))
        for index, (start, end) in enumerate(sorted(set(valid)), start=1):
            label = f"Jaktlag {index}" if index <= 2 else "Andre"
            periods.append(HuntingPeriod(start=start, end=end, label=label))
    return periods


def enrich_with_hunting_team(
    events: dict[str, dict[str, Any]],
    periods: Iterable[HuntingPeriod],
    timezone_name: str,
) -> dict[str, dict[str, Any]]:
    """Add neutral team/period fields; inclusive dates match the public map."""
    period_list = list(periods)
    enriched: dict[str, dict[str, Any]] = {}
    for event_id, source in events.items():
        event = dict(source)
        event_date = _local_date(event.get("Dato"), timezone_name)
        match = next(
            (
                period
                for period in period_list
                if event_date is not None and period.start <= event_date <= period.end
            ),
            None,
        )
        event["_jaktlag"] = match.label if match else "Andre"
        if match:
            event["_jaktperiode_start"] = match.start.isoformat()
            event["_jaktperiode_slutt"] = match.end.isoformat()
        enriched[event_id] = event
    return enriched


def stable_event_id(event: dict[str, Any]) -> str:
    storvilt_id = event.get("StorviltID")
    if storvilt_id is not None and str(storvilt_id).strip():
        return str(storvilt_id).strip()
    global_id = str(event.get("GlobalID") or "").strip("{} ")
    if global_id:
        return "global-" + global_id.lower()
    object_id = event.get("OBJECTID")
    if object_id is not None:
        return f"object-{object_id}"
    raise CollectorError("Fant en ArcGIS-rad uten StorviltID, GlobalID eller OBJECTID")


def _revision_rank(event: dict[str, Any]) -> tuple[int, int, int]:
    return (
        _as_int(event.get("last_edited_date")) or -1,
        _as_int(event.get("created_date")) or -1,
        _as_int(event.get("OBJECTID")) or -1,
    )


def deduplicate_events(events: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Keep the newest ArcGIS revision for each logical StorviltID."""
    unique: dict[str, dict[str, Any]] = {}
    for event in events:
        event_id = stable_event_id(event)
        existing = unique.get(event_id)
        if existing is None or _revision_rank(event) > _revision_rank(existing):
            unique[event_id] = event
    return unique


def parse_positive_number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        parsed = float(value)
    else:
        text = str(value).strip().replace("\u00a0", "").replace(" ", "")
        if not text:
            return None
        if "," in text and "." in text:
            if text.rfind(",") > text.rfind("."):
                text = text.replace(".", "").replace(",", ".")
            else:
                text = text.replace(",", "")
        else:
            text = text.replace(",", ".")
        try:
            parsed = float(text)
        except ValueError:
            return None
    return parsed if parsed > 0 else None


def _as_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def event_fingerprint(event: dict[str, Any]) -> str:
    canonical = json.dumps(
        event, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _escape_measurement(value: str) -> str:
    return value.replace("\\", "\\\\").replace(",", "\\,").replace(" ", "\\ ")


def _escape_key(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace(",", "\\,")
        .replace("=", "\\=")
        .replace(" ", "\\ ")
    )


def _escape_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _field_string(value: Any) -> str:
    return f'"{_escape_string(str(value))}"'


def build_line(event_id: str, event: dict[str, Any], config: Config) -> str:
    timestamp_ms = _as_int(event.get("Dato"))
    if timestamp_ms is None or timestamp_ms <= 0:
        raise CollectorError(f"Felling {event_id} mangler gyldig Dato")

    tags = {
        "art": config.art,
        "jaktfelt": config.jaktfelt_name,
        "jaktfelt_id": config.jaktfelt_id,
        "storvilt_id": event_id,
    }
    fields: dict[str, str] = {
        "felling": "1i",
        "jaktlag": _field_string(event.get("_jaktlag") or "Andre"),
        "kategori": _field_string(event.get("Kategori") or "Ukjent"),
        "kategori_skutt": _field_string(event.get("Kategoriskutt") or "Ukjent"),
    }

    for source_name, field_name in (
        ("_jaktperiode_start", "jaktperiode_start"),
        ("_jaktperiode_slutt", "jaktperiode_slutt"),
    ):
        value = event.get(source_name)
        if value:
            fields[field_name] = _field_string(value)

    raw_weight = event.get("Slaktevekt")
    parsed_weight = parse_positive_number(raw_weight)
    fields["slaktevekt_gyldig"] = "true" if parsed_weight is not None else "false"
    if raw_weight is not None and str(raw_weight).strip():
        fields["slaktevekt_raw"] = _field_string(raw_weight)
    if parsed_weight is not None:
        fields["slaktevekt"] = repr(parsed_weight)

    controlled_weight = parse_positive_number(event.get("Kontrollert_vekt"))
    if controlled_weight is not None:
        fields["kontrollert_vekt"] = repr(controlled_weight)

    for source_name, field_name in (
        ("OBJECTID", "object_id"),
        ("created_date", "source_created_ms"),
        ("last_edited_date", "source_last_edited_ms"),
    ):
        numeric = _as_int(event.get(source_name))
        if numeric is not None:
            fields[field_name] = f"{numeric}i"

    for source_name, field_name in (
        ("GlobalID", "global_id"),
        ("HjorteviltID", "hjortevilt_id"),
        ("Dato_Tekst", "dato_tekst"),
    ):
        value = event.get(source_name)
        if value is not None and str(value).strip():
            fields[field_name] = _field_string(value)

    tag_text = ",".join(
        f"{_escape_key(key)}={_escape_key(value)}" for key, value in sorted(tags.items())
    )
    field_text = ",".join(
        f"{_escape_key(key)}={value}" for key, value in sorted(fields.items())
    )
    timestamp_ns = timestamp_ms * 1_000_000
    return f"{_escape_measurement(MEASUREMENT)},{tag_text} {field_text} {timestamp_ns}"


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": 1, "events": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CollectorError(f"Kunne ikke lese state-fil {path}: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("events", {}), dict):
        raise CollectorError(f"Ugyldig state-fil: {path}")
    return data


def save_state(path: Path, events: dict[str, dict[str, Any]]) -> None:
    state_events = {
        event_id: {
            "fingerprint": event_fingerprint(event),
            "timestamp_ms": _as_int(event.get("Dato")),
        }
        for event_id, event in sorted(events.items())
    }
    payload = {"version": 1, "events": state_events}
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=path.parent, delete=False
        ) as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            temporary = Path(handle.name)
        os.replace(temporary, path)
    except OSError as exc:
        raise CollectorError(f"Kunne ikke lagre state-fil {path}: {exc}") from exc


def changed_events(
    current: dict[str, dict[str, Any]], state: dict[str, Any], force: bool = False
) -> dict[str, dict[str, Any]]:
    previous = state.get("events", {})
    return {
        event_id: event
        for event_id, event in current.items()
        if force
        or event_id not in previous
        or previous[event_id].get("fingerprint") != event_fingerprint(event)
    }


def _chunks(values: list[str], size: int) -> Iterable[list[str]]:
    for index in range(0, len(values), size):
        yield values[index : index + size]


def write_influx(lines: list[str], config: Config) -> None:
    endpoint = config.influx_url + "/api/v2/write?" + urllib.parse.urlencode(
        {
            "org": config.influx_org,
            "bucket": config.influx_bucket,
            "precision": "ns",
        }
    )
    for batch_number, batch in enumerate(_chunks(lines, config.batch_size), start=1):
        request = urllib.request.Request(
            endpoint,
            data=("\n".join(batch) + "\n").encode("utf-8"),
            method="POST",
            headers={
                "Authorization": f"Token {config.influx_token}",
                "Content-Type": "text/plain; charset=utf-8",
                "User-Agent": "statskog-elg-collector/1.0",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=config.timeout_seconds) as response:
                if response.status != 204:
                    raise CollectorError(
                        f"InfluxDB returnerte HTTP {response.status} for batch {batch_number}"
                    )
        except urllib.error.HTTPError as exc:
            detail = exc.read(1024).decode("utf-8", errors="replace")
            raise CollectorError(
                f"InfluxDB avviste batch {batch_number}: HTTP {exc.code}: {detail}"
            ) from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise CollectorError(
                f"Kunne ikke skrive batch {batch_number} til InfluxDB: {exc}"
            ) from exc


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check-api",
        action="store_true",
        help="hent, valider og oppsummer Statskog-data uten å kontakte InfluxDB",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="skriv line protocol til stdout uten Influx-skriving eller state-endring",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="skriv alle unike hendelser selv om lokal state sier de er uendret",
    )
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args(argv)


def run(argv: list[str]) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    config = Config.from_env(require_influx=not (args.check_api or args.dry_run))
    source_rows = fetch_events(config)
    unique = deduplicate_events(source_rows)
    duplicate_count = len(source_rows) - len(unique)
    LOG.info(
        "Statskog returnerte %d rader, %d unike fellinger (%d duplikater)",
        len(source_rows),
        len(unique),
        duplicate_count,
    )

    years = {
        event_date.year
        for event in unique.values()
        if (event_date := _local_date(event.get("Dato"), config.local_timezone))
        is not None
    }
    jaktfelt_unik_id = fetch_jaktfelt_unik_id(config)
    periods = fetch_hunting_periods(config, jaktfelt_unik_id, years)
    unique = enrich_with_hunting_team(unique, periods, config.local_timezone)
    LOG.info(
        "Fant %d jaktlagsperioder for offentlig felt-ID %d",
        len(periods),
        jaktfelt_unik_id,
    )

    if args.check_api:
        print(
            json.dumps(
                {
                    "jaktfelt_id": config.jaktfelt_id,
                    "art": config.art,
                    "raw_rows": len(source_rows),
                    "unique_events": len(unique),
                    "duplicate_rows": duplicate_count,
                    "years": sorted(years),
                    "hunting_periods": len(periods),
                    "team_counts": {
                        label: sum(
                            1 for event in unique.values() if event["_jaktlag"] == label
                        )
                        for label in ("Jaktlag 1", "Jaktlag 2", "Andre")
                    },
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    state = load_state(config.state_file)
    pending = changed_events(unique, state, force=args.force)
    lines = [build_line(event_id, event, config) for event_id, event in pending.items()]

    if args.dry_run:
        if lines:
            print("\n".join(lines))
        LOG.info("Dry-run: %d punkter ville blitt skrevet", len(lines))
        return 0

    if lines:
        write_influx(lines, config)
        LOG.info("Skrev %d nye eller endrede fellinger til InfluxDB", len(lines))
    else:
        LOG.info("Ingen nye eller endrede fellinger")
    save_state(config.state_file, unique)
    return 0


def main() -> None:
    try:
        raise SystemExit(run(sys.argv[1:]))
    except CollectorError as exc:
        LOG.error("%s", exc)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
