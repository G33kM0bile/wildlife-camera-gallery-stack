#!/usr/bin/python3
"""Admin-only web editor for wildlife-camera metadata configuration."""

from __future__ import annotations

from base64 import b64encode
from datetime import datetime, timedelta, timezone
from email.utils import formatdate
import hmac
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import mimetypes
import os
from pathlib import Path
import secrets
import tempfile
import threading
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen


BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
CONFIG_PATH = Path(
    os.environ.get("CAMERA_ADMIN_CONFIG", "/etc/viltkamera-metadata/cameras.json")
)
HISTORY_DIR = Path(
    os.environ.get("CAMERA_ADMIN_HISTORY", "/etc/viltkamera-metadata/history")
)
SFTPGO_API_URL = os.environ.get("SFTPGO_API_URL", "http://127.0.0.1:8080").rstrip("/")
BIND_ADDRESS = os.environ.get("CAMERA_ADMIN_BIND", "127.0.0.1")
PORT = int(os.environ.get("CAMERA_ADMIN_PORT", "9095"))
SECURE_COOKIE = os.environ.get("CAMERA_ADMIN_SECURE_COOKIE", "0") == "1"
SESSION_SECONDS = 8 * 60 * 60
MAX_BODY = 64 * 1024
EXPECTED_IDS = tuple(f"hc960-{number:02d}" for number in range(1, 6))

CONFIG_LOCK = threading.RLock()
SESSION_LOCK = threading.RLock()
SESSIONS: dict[str, dict[str, Any]] = {}
LOGIN_FAILURES: dict[str, list[float]] = {}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_utc(value: datetime | None = None) -> str:
    return (value or utc_now()).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_config() -> dict[str, Any]:
    with CONFIG_PATH.open("r", encoding="utf-8") as handle:
        config = json.load(handle)
    if config.get("schema_version") != 1 or not isinstance(config.get("cameras"), list):
        raise ValueError("Konfigurasjonsfilen har et ukjent format")
    for camera in config["cameras"]:
        if not isinstance(camera, dict):
            continue
        camera.setdefault("subject", camera.get("title", ""))
        camera.setdefault("comment", "")
        camera.setdefault(
            "tags",
            ["viltkamera", camera.get("id", ""), camera.get("location", "")],
        )
    return config


def clean_text(value: Any, label: str, maximum: int) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} må være tekst")
    result = " ".join(value.strip().split())
    if not result:
        raise ValueError(f"{label} kan ikke være tom")
    if len(result) > maximum:
        raise ValueError(f"{label} kan ha maksimalt {maximum} tegn")
    if any(ord(character) < 32 for character in result):
        raise ValueError(f"{label} inneholder ugyldige tegn")
    return result


def clean_optional_text(value: Any, label: str, maximum: int) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} må være tekst")
    result = " ".join(value.strip().split())
    if len(result) > maximum:
        raise ValueError(f"{label} kan ha maksimalt {maximum} tegn")
    if any(ord(character) < 32 for character in result):
        raise ValueError(f"{label} inneholder ugyldige tegn")
    return result


def clean_tags(value: Any, label: str) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{label} må være en liste")
    if len(value) > 30:
        raise ValueError(f"{label} kan inneholde maksimalt 30 tagger")
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in value:
        tag = clean_optional_text(item, label, 64)
        if not tag:
            continue
        normalized = tag.casefold()
        if normalized not in seen:
            cleaned.append(tag)
            seen.add(normalized)
    return cleaned


def clean_coordinate(value: Any, label: str, minimum: float, maximum: float) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{label} må være et tall")
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{label} må være et tall") from error
    if not math.isfinite(number) or not minimum <= number <= maximum:
        raise ValueError(f"{label} må være mellom {minimum:g} og {maximum:g}")
    return round(number, 7)


def validate_config(payload: Any, current: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict) or not isinstance(payload.get("cameras"), list):
        raise ValueError("Ugyldig konfigurasjon")
    cameras = payload["cameras"]
    if len(cameras) != len(EXPECTED_IDS):
        raise ValueError("Konfigurasjonen må inneholde nøyaktig fem kameraer")

    cleaned: list[dict[str, Any]] = []
    seen: set[str] = set()
    for position, camera in enumerate(cameras, start=1):
        if not isinstance(camera, dict):
            raise ValueError("Hvert kamera må være et objekt")
        camera_id = camera.get("id")
        if camera_id != EXPECTED_IDS[position - 1] or camera_id in seen:
            raise ValueError("Kamera-ID eller rekkefølge kan ikke endres")
        if camera.get("number") != position:
            raise ValueError("Kameranummer kan ikke endres")
        enabled = camera.get("enabled")
        if not isinstance(enabled, bool):
            raise ValueError(f"Aktiv-status for kamera {position} er ugyldig")
        seen.add(camera_id)
        cleaned.append(
            {
                "id": camera_id,
                "number": position,
                "enabled": enabled,
                "title": clean_text(camera.get("title"), f"Tittel for kamera {position}", 100),
                "subject": clean_optional_text(
                    camera.get("subject", ""), f"Emne for kamera {position}", 160
                ),
                "comment": clean_optional_text(
                    camera.get("comment", ""), f"Kommentar for kamera {position}", 500
                ),
                "tags": clean_tags(camera.get("tags", []), f"Tagger for kamera {position}"),
                "location": clean_text(
                    camera.get("location"), f"Stedsnavn for kamera {position}", 80
                ),
                "latitude": clean_coordinate(
                    camera.get("latitude"), f"Breddegrad for kamera {position}", -90, 90
                ),
                "longitude": clean_coordinate(
                    camera.get("longitude"), f"Lengdegrad for kamera {position}", -180, 180
                ),
            }
        )

    managed: list[str] = []
    candidates = list(current.get("managed_keywords", []))
    candidates.extend(["viltkamera", *EXPECTED_IDS])
    candidates.extend(
        camera.get("location", "")
        for camera in current.get("cameras", [])
        if isinstance(camera, dict)
    )
    candidates.extend(camera["location"] for camera in cleaned)
    candidates.extend(
        tag
        for camera in current.get("cameras", [])
        if isinstance(camera, dict)
        for tag in camera.get("tags", [])
        if isinstance(tag, str)
    )
    candidates.extend(tag for camera in cleaned for tag in camera["tags"])
    for candidate in candidates:
        if isinstance(candidate, str) and candidate and candidate not in managed:
            managed.append(candidate)
    if len(managed) > 100:
        managed = managed[-100:]

    return {
        "schema_version": 1,
        "revision": int(current.get("revision", 0)) + 1,
        "updated_at": iso_utc(),
        "managed_keywords": managed,
        "cameras": cleaned,
    }


def write_json_atomic(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary_path, 0o660)
        os.replace(temporary_path, path)
        try:
            directory_fd = os.open(path.parent, os.O_RDONLY)
        except OSError:
            # Windows cannot open directory handles this way. Debian can and
            # uses the fsync below to make the atomic rename durable.
            directory_fd = None
        if directory_fd is not None:
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
    finally:
        temporary_path.unlink(missing_ok=True)


def save_config(payload: Any) -> dict[str, Any]:
    with CONFIG_LOCK:
        current = load_config()
        updated = validate_config(payload, current)
        HISTORY_DIR.mkdir(parents=True, exist_ok=True)
        history_name = (
            f"cameras-r{int(current.get('revision', 0)):04d}-"
            f"{utc_now().strftime('%Y%m%dT%H%M%SZ')}.json"
        )
        write_json_atomic(HISTORY_DIR / history_name, current)
        write_json_atomic(CONFIG_PATH, updated)
        history_files = sorted(HISTORY_DIR.glob("cameras-r*.json"), reverse=True)
        for old_file in history_files[20:]:
            old_file.unlink(missing_ok=True)
        return updated


def authenticate_admin(username: str, password: str) -> datetime:
    credentials = b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
    request = Request(
        f"{SFTPGO_API_URL}/api/v2/token",
        headers={"Accept": "application/json", "Authorization": f"Basic {credentials}"},
        method="GET",
    )
    try:
        with urlopen(request, timeout=6) as response:
            result = json.load(response)
    except HTTPError as error:
        if error.code in (401, 403):
            raise PermissionError("Ugyldig administratornavn eller passord") from error
        raise ConnectionError("SFTPGo avviste innloggingen") from error
    except (URLError, TimeoutError, json.JSONDecodeError) as error:
        raise ConnectionError("Kunne ikke kontakte SFTPGo") from error
    if not isinstance(result.get("access_token"), str):
        raise ConnectionError("SFTPGo returnerte et ugyldig svar")
    expiry = utc_now() + timedelta(seconds=SESSION_SECONDS)
    expires_at = result.get("expires_at")
    if isinstance(expires_at, str):
        try:
            parsed = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            expiry = min(expiry, parsed.astimezone(timezone.utc))
        except ValueError:
            pass
    return expiry


def new_session(username: str, expiry: datetime) -> tuple[str, str]:
    token = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(24)
    with SESSION_LOCK:
        SESSIONS[token] = {"username": username, "csrf": csrf, "expires": expiry.timestamp()}
    return token, csrf


def session_from_cookie(cookie_header: str | None) -> tuple[str, dict[str, Any]] | None:
    if not cookie_header:
        return None
    cookie = SimpleCookie()
    try:
        cookie.load(cookie_header)
    except Exception:
        return None
    morsel = cookie.get("camera_admin_session")
    if morsel is None:
        return None
    token = morsel.value
    with SESSION_LOCK:
        session = SESSIONS.get(token)
        if not session:
            return None
        if float(session["expires"]) <= time.time():
            SESSIONS.pop(token, None)
            return None
        return token, dict(session)


def login_allowed(ip_address: str) -> tuple[bool, int]:
    now = time.time()
    with SESSION_LOCK:
        recent = [stamp for stamp in LOGIN_FAILURES.get(ip_address, []) if stamp > now - 900]
        LOGIN_FAILURES[ip_address] = recent
        if len(recent) >= 5:
            return False, max(1, int(900 - (now - recent[0])))
    return True, 0


class CameraAdminHandler(BaseHTTPRequestHandler):
    server_version = "ViltkameraCameraAdmin/1.0"

    def log_message(self, message: str, *args: Any) -> None:
        print(f"{self.address_string()} - {message % args}", flush=True)

    def security_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Permissions-Policy", "geolocation=(), camera=(), microphone=()")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; "
            "style-src 'self'; style-src-attr 'unsafe-inline'; "
            "img-src 'self' data: "
            "https://wms.geonorge.no; connect-src 'self'; "
            "frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
        )

    def send_bytes(
        self,
        status: int,
        body: bytes,
        content_type: str,
        *,
        cache_control: str = "no-store",
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self.send_response(status)
        self.security_headers()
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache_control)
        if extra_headers:
            for name, value in extra_headers.items():
                self.send_header(name, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def send_json(self, status: int, value: Any, **kwargs: Any) -> None:
        body = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_bytes(status, body, "application/json; charset=utf-8", **kwargs)

    def send_error_json(self, status: int, message: str, **kwargs: Any) -> None:
        self.send_json(status, {"error": message}, **kwargs)

    def read_body(self) -> bytes:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as error:
            raise ValueError("Ugyldig innholdslengde") from error
        if length < 0 or length > MAX_BODY:
            raise ValueError("Forespørselen er for stor")
        return self.rfile.read(length)

    def require_session(self) -> tuple[str, dict[str, Any]] | None:
        result = session_from_cookie(self.headers.get("Cookie"))
        if not result:
            self.send_error_json(HTTPStatus.UNAUTHORIZED, "Innlogging kreves")
            return None
        return result

    def csrf_matches(self, session: dict[str, Any]) -> bool:
        provided = self.headers.get("X-CSRF-Token", "")
        return bool(provided) and hmac.compare_digest(provided, str(session["csrf"]))

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/healthz":
            self.send_json(HTTPStatus.OK, {"status": "ok"})
            return
        if path == "/api/config":
            authenticated = self.require_session()
            if not authenticated:
                return
            _, session = authenticated
            try:
                config = load_config()
            except (OSError, ValueError, json.JSONDecodeError):
                self.send_error_json(HTTPStatus.INTERNAL_SERVER_ERROR, "Kunne ikke lese konfigurasjonen")
                return
            self.send_json(
                HTTPStatus.OK,
                {"config": config, "csrf": session["csrf"], "username": session["username"]},
            )
            return
        if path == "/":
            self.serve_static("index.html", cache_control="no-store")
            return
        if path.startswith("/static/"):
            self.serve_static(path.removeprefix("/static/"), cache_control="public, max-age=3600")
            return
        self.send_error_json(HTTPStatus.NOT_FOUND, "Ikke funnet")

    def serve_static(self, relative_name: str, *, cache_control: str) -> None:
        try:
            candidate = (STATIC_DIR / relative_name).resolve(strict=True)
            candidate.relative_to(STATIC_DIR.resolve())
        except (OSError, ValueError):
            self.send_error_json(HTTPStatus.NOT_FOUND, "Ikke funnet")
            return
        if not candidate.is_file():
            self.send_error_json(HTTPStatus.NOT_FOUND, "Ikke funnet")
            return
        content_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type in ("application/javascript", "application/json"):
            content_type += "; charset=utf-8"
        self.send_bytes(
            HTTPStatus.OK,
            candidate.read_bytes(),
            content_type,
            cache_control=cache_control,
            extra_headers={"Last-Modified": formatdate(candidate.stat().st_mtime, usegmt=True)},
        )

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/login":
            self.handle_login()
            return
        if path == "/api/logout":
            self.handle_logout()
            return
        if path == "/api/config":
            self.handle_save()
            return
        self.send_error_json(HTTPStatus.NOT_FOUND, "Ikke funnet")

    def handle_login(self) -> None:
        allowed, retry_after = login_allowed(self.client_address[0])
        if not allowed:
            self.send_error_json(
                HTTPStatus.TOO_MANY_REQUESTS,
                "For mange mislykkede forsøk. Prøv igjen senere.",
                extra_headers={"Retry-After": str(retry_after)},
            )
            return
        try:
            values = parse_qs(self.read_body().decode("utf-8"), keep_blank_values=True)
            username = values.get("username", [""])[0].strip()
            password = values.get("password", [""])[0]
            if not username or len(username) > 128 or not password or len(password) > 512:
                raise PermissionError("Ugyldig administratornavn eller passord")
            expiry = authenticate_admin(username, password)
        except PermissionError as error:
            with SESSION_LOCK:
                LOGIN_FAILURES.setdefault(self.client_address[0], []).append(time.time())
            self.send_error_json(HTTPStatus.UNAUTHORIZED, str(error))
            return
        except (ConnectionError, ValueError, UnicodeDecodeError) as error:
            self.send_error_json(HTTPStatus.BAD_GATEWAY, str(error))
            return
        with SESSION_LOCK:
            LOGIN_FAILURES.pop(self.client_address[0], None)
        token, csrf = new_session(username, expiry)
        cookie = (
            f"camera_admin_session={token}; Path=/; HttpOnly; SameSite=Strict; "
            f"Max-Age={max(60, int(expiry.timestamp() - time.time()))}"
        )
        if SECURE_COOKIE:
            cookie += "; Secure"
        self.send_json(
            HTTPStatus.OK,
            {"ok": True, "csrf": csrf, "username": username},
            extra_headers={"Set-Cookie": cookie},
        )

    def handle_logout(self) -> None:
        authenticated = self.require_session()
        if not authenticated:
            return
        token, session = authenticated
        if not self.csrf_matches(session):
            self.send_error_json(HTTPStatus.FORBIDDEN, "Ugyldig sikkerhetstoken")
            return
        with SESSION_LOCK:
            SESSIONS.pop(token, None)
        cookie = "camera_admin_session=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0"
        if SECURE_COOKIE:
            cookie += "; Secure"
        self.send_json(HTTPStatus.OK, {"ok": True}, extra_headers={"Set-Cookie": cookie})

    def handle_save(self) -> None:
        authenticated = self.require_session()
        if not authenticated:
            return
        _, session = authenticated
        if not self.csrf_matches(session):
            self.send_error_json(HTTPStatus.FORBIDDEN, "Ugyldig sikkerhetstoken")
            return
        try:
            payload = json.loads(self.read_body().decode("utf-8"))
            updated = save_config(payload)
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as error:
            self.send_error_json(HTTPStatus.BAD_REQUEST, str(error))
            return
        except OSError:
            self.send_error_json(HTTPStatus.INTERNAL_SERVER_ERROR, "Kunne ikke lagre konfigurasjonen")
            return
        self.send_json(HTTPStatus.OK, {"ok": True, "config": updated})


def run() -> None:
    server = ThreadingHTTPServer((BIND_ADDRESS, PORT), CameraAdminHandler)
    server.daemon_threads = True
    print(f"Kameraoppsett lytter på http://{BIND_ADDRESS}:{PORT}", flush=True)
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    run()
