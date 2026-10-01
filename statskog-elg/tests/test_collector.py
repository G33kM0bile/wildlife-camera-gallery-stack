import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).resolve().parents[1] / "collector.py"
SPEC = importlib.util.spec_from_file_location("statskog_elg_collector", MODULE_PATH)
collector = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = collector
SPEC.loader.exec_module(collector)


def config(state_file: Path | None = None):
    return collector.Config(
        arcgis_url=collector.DEFAULT_ARCGIS_URL,
        arcgis_layer=0,
        jaktfelt_lookup_layer=4,
        jaktlag_period_layer=8,
        jaktfelt_id="1840J0096",
        jaktfelt_name="Storjord Øst",
        art="Elg",
        influx_url="http://influx.invalid:8086",
        influx_token="secret",
        influx_org="Minsin",
        influx_bucket="Wildlife",
        state_file=state_file or Path("state.json"),
        timeout_seconds=30,
        page_size=1000,
        batch_size=500,
        local_timezone="Europe/Oslo",
    )


class CollectorTests(unittest.TestCase):
    def test_parse_norwegian_weight(self):
        self.assertEqual(59.9, collector.parse_positive_number("59,9"))
        self.assertEqual(1234.5, collector.parse_positive_number("1.234,5"))
        self.assertIsNone(collector.parse_positive_number("0"))
        self.assertIsNone(collector.parse_positive_number("ikke oppgitt"))

    def test_deduplicate_uses_latest_revision(self):
        rows = [
            {"StorviltID": 50692, "OBJECTID": 227196, "last_edited_date": 10},
            {"StorviltID": 50692, "OBJECTID": 227554, "last_edited_date": 11},
            {"StorviltID": 60200, "OBJECTID": 360770, "last_edited_date": 20},
        ]
        result = collector.deduplicate_events(rows)
        self.assertEqual(2, len(result))
        self.assertEqual(227554, result["50692"]["OBJECTID"])

    def test_line_protocol_has_stable_identity_and_numeric_weight(self):
        row = {
            "StorviltID": 60200,
            "OBJECTID": 360770,
            "Dato": 1730937600000,
            "Kategori": "Ungdyr (20)",
            "Kategoriskutt": "Årskalv okse (11)",
            "Slaktevekt": "59,9",
            "Kontrollert_vekt": None,
            "GlobalID": "{75250C4B-E457-4DE9-8BF7-0391E6277293}",
            "_jaktlag": "Jaktlag 1",
            "_jaktperiode_start": "2024-09-25",
            "_jaktperiode_slutt": "2024-10-09",
        }
        line = collector.build_line("60200", row, config())
        self.assertTrue(line.startswith("elg_felling,"))
        self.assertIn("jaktfelt_id=1840J0096", line)
        self.assertIn("storvilt_id=60200", line)
        self.assertIn("slaktevekt=59.9", line)
        self.assertIn('kategori_skutt="Årskalv okse (11)"', line)
        self.assertIn('jaktlag="Jaktlag 1"', line)
        self.assertIn('jaktperiode_start="2024-09-25"', line)
        self.assertTrue(line.endswith(" 1730937600000000000"))

    def test_zero_weight_is_preserved_but_not_numeric(self):
        row = {
            "StorviltID": 45353,
            "Dato": 1633810131000,
            "Kategori": "10. Årskalv",
            "Kategoriskutt": "12. Årskalv ku",
            "Slaktevekt": "0",
        }
        line = collector.build_line("45353", row, config())
        self.assertIn('slaktevekt_raw="0"', line)
        self.assertIn("slaktevekt_gyldig=false", line)
        self.assertNotIn("slaktevekt=", line)

    def test_missing_storvilt_id_has_stable_fallback(self):
        self.assertEqual(
            "global-abcdef",
            collector.stable_event_id({"GlobalID": "{ABCDEF}", "OBJECTID": 3}),
        )
        self.assertEqual("object-3", collector.stable_event_id({"OBJECTID": 3}))

    def test_unchanged_event_is_not_pending(self):
        row = {"StorviltID": 1, "Dato": 1000, "Kategori": "Kalv"}
        current = {"1": row}
        state = {
            "version": 1,
            "events": {"1": {"fingerprint": collector.event_fingerprint(row)}},
        }
        self.assertEqual({}, collector.changed_events(current, state))
        row["Kategori"] = "Ungdyr"
        self.assertEqual({"1": row}, collector.changed_events(current, state))

    def test_hunting_period_boundaries_are_inclusive(self):
        oslo = collector.ZoneInfo("Europe/Oslo")
        periods = [
            collector.HuntingPeriod(
                collector.date(2026, 9, 25),
                collector.date(2026, 10, 9),
                "Jaktlag 1",
            ),
            collector.HuntingPeriod(
                collector.date(2026, 10, 10),
                collector.date(2026, 10, 31),
                "Jaktlag 2",
            ),
        ]

        def epoch_ms(year, month, day):
            return int(collector.datetime(year, month, day, 12, tzinfo=oslo).timestamp() * 1000)

        rows = {
            "a": {"Dato": epoch_ms(2026, 9, 25)},
            "b": {"Dato": epoch_ms(2026, 10, 9)},
            "c": {"Dato": epoch_ms(2026, 10, 10)},
            "d": {"Dato": epoch_ms(2026, 11, 1)},
        }
        result = collector.enrich_with_hunting_team(rows, periods, "Europe/Oslo")
        self.assertEqual("Jaktlag 1", result["a"]["_jaktlag"])
        self.assertEqual("Jaktlag 1", result["b"]["_jaktlag"])
        self.assertEqual("Jaktlag 2", result["c"]["_jaktlag"])
        self.assertEqual("Andre", result["d"]["_jaktlag"])

    def test_team_enrichment_changes_event_fingerprint(self):
        first = {"Dato": 1, "_jaktlag": "Jaktlag 1"}
        second = {"Dato": 1, "_jaktlag": "Jaktlag 2"}
        self.assertNotEqual(
            collector.event_fingerprint(first), collector.event_fingerprint(second)
        )

    def test_state_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            rows = {"1": {"StorviltID": 1, "Dato": 1000}}
            collector.save_state(path, rows)
            state = collector.load_state(path)
            self.assertEqual(1, state["version"])
            self.assertEqual(1000, state["events"]["1"]["timestamp_ms"])

    def test_influx_write_uses_scoped_endpoint_and_token(self):
        response = mock.MagicMock()
        response.status = 204
        response.__enter__.return_value = response
        response.__exit__.return_value = False
        with mock.patch.object(
            collector.urllib.request, "urlopen", return_value=response
        ) as call:
            collector.write_influx(["measurement value=1i 1"], config())
        request = call.call_args.args[0]
        self.assertIn("/api/v2/write?", request.full_url)
        self.assertIn("org=Minsin", request.full_url)
        self.assertIn("bucket=Wildlife", request.full_url)
        self.assertEqual("Token secret", request.headers["Authorization"])
        self.assertEqual(b"measurement value=1i 1\n", request.data)


if __name__ == "__main__":
    unittest.main()
