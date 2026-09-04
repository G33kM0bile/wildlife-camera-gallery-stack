from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

import app  # noqa: E402
import importlib.util  # noqa: E402


def load_tagger():
    spec = importlib.util.spec_from_file_location(
        "viltkamera_metadata", PROJECT_DIR / "viltkamera-metadata.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self, *_):
        return json.dumps(self.payload).encode("utf-8")


class CameraAdminTests(unittest.TestCase):
    def setUp(self):
        with (PROJECT_DIR / "config" / "cameras.example.json").open(encoding="utf-8") as handle:
            self.config = json.load(handle)

    def test_valid_update_is_sanitized_and_revisioned(self):
        payload = {"cameras": copy.deepcopy(self.config["cameras"])}
        payload["cameras"][2]["title"] = "  Kamera 3   |   Ny post  "
        payload["cameras"][2]["location"] = "Ny post"
        payload["cameras"][2]["subject"] = "  Nytt   emne  "
        payload["cameras"][2]["comment"] = "  Elg   observert  "
        payload["cameras"][2]["tags"] = ["Elg", " elg ", "Natt"]
        updated = app.validate_config(payload, self.config)
        self.assertEqual(updated["revision"], 2)
        self.assertEqual(updated["cameras"][2]["title"], "Kamera 3 | Ny post")
        self.assertEqual(updated["cameras"][2]["subject"], "Nytt emne")
        self.assertEqual(updated["cameras"][2]["comment"], "Elg observert")
        self.assertEqual(updated["cameras"][2]["tags"], ["Elg", "Natt"])
        self.assertIn("Forest edge", updated["managed_keywords"])
        self.assertIn("Ny post", updated["managed_keywords"])
        self.assertIn("Elg", updated["managed_keywords"])

    def test_camera_identity_cannot_change(self):
        payload = {"cameras": copy.deepcopy(self.config["cameras"])}
        payload["cameras"][0]["id"] = "hc960-05"
        with self.assertRaisesRegex(ValueError, "Kamera-ID"):
            app.validate_config(payload, self.config)

    def test_invalid_coordinate_is_rejected(self):
        payload = {"cameras": copy.deepcopy(self.config["cameras"])}
        payload["cameras"][0]["latitude"] = 91
        with self.assertRaisesRegex(ValueError, "Breddegrad"):
            app.validate_config(payload, self.config)

    def test_atomic_json_write(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cameras.json"
            app.write_json_atomic(path, self.config)
            with path.open(encoding="utf-8") as handle:
                self.assertEqual(json.load(handle), self.config)
            if os.name != "nt":
                self.assertEqual(path.stat().st_mode & 0o777, 0o660)

    def test_leaflet_assets_are_self_hosted(self):
        html = (PROJECT_DIR / "static" / "index.html").read_text(encoding="utf-8")
        self.assertNotIn("unpkg.com", html)
        self.assertIn("/static/vendor/leaflet/leaflet.css", html)
        self.assertIn("/static/vendor/leaflet/leaflet.js", html)

    @patch("app.urlopen")
    def test_sftpgo_admin_login_uses_token_endpoint(self, mocked_urlopen):
        mocked_urlopen.return_value = FakeResponse(
            {"access_token": "token", "expires_at": "2030-01-01T00:00:00Z"}
        )
        expiry = app.authenticate_admin("admin", "secret")
        request = mocked_urlopen.call_args.args[0]
        self.assertTrue(request.full_url.endswith("/api/v2/token"))
        self.assertTrue(request.headers["Authorization"].startswith("Basic "))
        self.assertGreater(expiry.timestamp(), 0)


class MetadataTaggerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tagger = load_tagger()

    def test_matching_metadata_is_idempotent(self):
        camera = {
            "id": "hc960-01",
            "location": "North crossing",
            "title": "Camera 1 | North crossing",
            "subject": "Camera 1 | North crossing",
            "comment": "Fast plassering",
            "tags": ["wildlife-camera", "camera-01", "North crossing"],
            "latitude": 60.001,
            "longitude": 10.001,
        }
        current = (
            60.0010000001,
            10.0010000001,
            "North crossing",
            "wildlife-camera, camera-01, North crossing",
            "Camera 1 | North crossing",
            "Camera 1 | North crossing",
            "Fast plassering",
        )
        self.assertTrue(
            self.tagger.metadata_matches(
                current,
                camera,
                ["wildlife-camera", "camera-01", "North crossing", "Upper trail"],
            )
        )

    def test_stale_managed_keyword_forces_rewrite(self):
        camera = {
            "id": "hc960-05",
            "location": "Upper trail",
            "title": "Camera 5 | Upper trail",
            "subject": "Camera 5 | Upper trail",
            "comment": "",
            "tags": ["wildlife-camera", "camera-05", "Upper trail"],
            "latitude": 60.005,
            "longitude": 10.005,
        }
        current = (
            60.005,
            10.005,
            "Upper trail",
            "wildlife-camera, camera-05, Upper trail, camera-01",
            "Camera 5 | Upper trail",
            "Camera 5 | Upper trail",
            "",
        )
        self.assertFalse(
            self.tagger.metadata_matches(
                current, camera, ["wildlife-camera", "camera-01", "camera-05", "Upper trail"]
            )
        )


if __name__ == "__main__":
    unittest.main()
