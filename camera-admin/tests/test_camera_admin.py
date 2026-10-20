from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse


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
        with tempfile.TemporaryDirectory(dir=PROJECT_DIR) as directory:
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

    def test_oidc_login_uses_authorization_code_pkce(self):
        with tempfile.TemporaryDirectory(dir=PROJECT_DIR) as directory:
            secret_file = Path(directory) / "client-secret"
            secret_file.write_text("secret\n", encoding="utf-8")
            discovery = {
                "issuer": "https://auth.example.test/auth/v1/",
                "authorization_endpoint": "https://auth.example.test/authorize",
                "token_endpoint": "https://auth.example.test/token",
                "userinfo_endpoint": "https://auth.example.test/userinfo",
            }
            with (
                patch.object(app, "OIDC_ISSUER", "https://auth.example.test/auth/v1"),
                patch.object(app, "OIDC_CLIENT_ID", "kamera"),
                patch.object(app, "OIDC_CLIENT_SECRET_FILE", secret_file),
                patch.object(app, "OIDC_REDIRECT_URI", "https://kamera.example.test/auth/oidc/callback"),
                patch.object(app, "OIDC_ALLOWED_USERS", frozenset({"ola"})),
                patch.object(app, "OIDC_DISCOVERY", discovery),
            ):
                app.OIDC_REQUESTS.clear()
                login_url = app.oidc_login_url()
        query = parse_qs(urlparse(login_url).query)
        self.assertEqual(query["response_type"], ["code"])
        self.assertEqual(query["code_challenge_method"], ["S256"])
        self.assertEqual(query["client_id"], ["kamera"])
        self.assertIn(query["state"][0], app.OIDC_REQUESTS)

    @patch("app.urlopen")
    def test_oidc_callback_uses_userinfo_and_allowlist(self, mocked_urlopen):
        mocked_urlopen.side_effect = [
            FakeResponse({"access_token": "access", "expires_in": 900}),
            FakeResponse({"sub": "stable-id", "preferred_username": "Ola"}),
        ]
        with tempfile.TemporaryDirectory(dir=PROJECT_DIR) as directory:
            secret_file = Path(directory) / "client-secret"
            secret_file.write_text("secret\n", encoding="utf-8")
            discovery = {
                "issuer": "https://auth.example.test/auth/v1/",
                "authorization_endpoint": "https://auth.example.test/authorize",
                "token_endpoint": "https://auth.example.test/token",
                "userinfo_endpoint": "https://auth.example.test/userinfo",
            }
            with (
                patch.object(app, "OIDC_CLIENT_ID", "kamera"),
                patch.object(app, "OIDC_CLIENT_SECRET_FILE", secret_file),
                patch.object(app, "OIDC_REDIRECT_URI", "https://kamera.example.test/auth/oidc/callback"),
                patch.object(app, "OIDC_ALLOWED_USERS", frozenset({"ola"})),
                patch.object(app, "OIDC_DISCOVERY", discovery),
            ):
                app.OIDC_REQUESTS.clear()
                app.OIDC_REQUESTS["state"] = {
                    "verifier": "verifier",
                    "nonce": "nonce",
                    "expires": time.time() + 60,
                }
                username, expiry = app.authenticate_oidc_callback(
                    {"state": ["state"], "code": ["code"]}
                )
        self.assertEqual(username, "Ola")
        self.assertGreater(expiry.timestamp(), time.time())
        token_request = mocked_urlopen.call_args_list[0].args[0]
        self.assertIn(b"code_verifier=verifier", token_request.data)
        user_request = mocked_urlopen.call_args_list[1].args[0]
        self.assertEqual(user_request.headers["Authorization"], "Bearer access")

    def test_hunting_ground_input_is_sanitized(self):
        updated = app.validate_hunting_ground(
            {"jaktfelt_id": " 1840J0096 ", "jaktfelt_name": "  Storjord   Øst "}
        )
        self.assertEqual("1840J0096", updated["jaktfelt_id"])
        self.assertEqual("Storjord Øst", updated["jaktfelt_name"])
        with self.assertRaisesRegex(ValueError, "Jaktfelt-ID"):
            app.validate_hunting_ground(
                {"jaktfelt_id": "1840J0096'", "jaktfelt_name": "Storjord Øst"}
            )

    @patch("app.urlopen")
    def test_oidc_group_membership_controls_new_users(self, mocked_urlopen):
        discovery = {
            "token_endpoint": "https://auth.example.test/token",
            "userinfo_endpoint": "https://auth.example.test/userinfo",
        }
        with (
            patch.object(app, "OIDC_ALLOWED_USERS", frozenset()),
            patch.object(app, "OIDC_ALLOWED_GROUPS", frozenset({"hunters", "admin"})),
            patch.object(app, "OIDC_DISCOVERY", discovery),
            patch.object(app, "oidc_client_secret", return_value="secret"),
        ):
            for groups, allowed in ((["hunters"], True), (["admin"], True),
                                    (["hunters", "admin"], True), ([], False),
                                    ("hunters", False), (["Hunters"], False),
                                    (["hunters-other"], False), (["hunters", 1], False),
                                    (None, False)):
                with self.subTest(groups=groups):
                    mocked_urlopen.side_effect = [
                        FakeResponse({"access_token": "access", "expires_in": 900}),
                        FakeResponse({"sub": "new-subject", "preferred_username": "new-hunter", "groups": groups}),
                    ]
                    app.OIDC_REQUESTS["group-state"] = {
                        "verifier": "verifier", "expires": time.time() + 60,
                    }
                    query = {"state": ["group-state"], "code": ["code"]}
                    if allowed:
                        username, _ = app.authenticate_oidc_callback(query)
                        self.assertEqual(username, "new-hunter")
                    else:
                        with self.assertRaises(PermissionError):
                            app.authenticate_oidc_callback(query)

    @patch("app.urlopen")
    def test_hunting_ground_lookup_uses_public_arcgis(self, mocked_urlopen):
        mocked_urlopen.return_value = FakeResponse(
            {
                "features": [
                    {
                        "attributes": {
                            "JaktfeltUnikID": 2202,
                            "JaktfeltID": "1840J0096",
                            "Feltnavn": "Storjord Øst",
                            "Art": "Elg",
                        }
                    }
                ]
            }
        )
        result = app.lookup_hunting_ground("1840J0096")
        self.assertEqual("Storjord Øst", result["statskog_name"])
        self.assertEqual(2202, result["statskog_unique_id"])
        request = mocked_urlopen.call_args.args[0]
        self.assertIn("/4/query?", request.full_url)
        self.assertIn("JaktfeltID", request.full_url)


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
