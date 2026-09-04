#!/usr/bin/python3
"""Attach configured wildlife-camera metadata to one newly uploaded image."""

from __future__ import annotations

import json
import logging
import math
import os
from pathlib import Path
import subprocess
import sys
from typing import Any


ROOT = Path(os.environ.get("VILTKAMERA_ROOT", "/srv/sftpgo/data")).resolve()
CONFIG_PATH = Path(
    os.environ.get("VILTKAMERA_CONFIG", "/etc/viltkamera-metadata/cameras.json")
)
EXIFTOOL = os.environ.get("EXIFTOOL", "/usr/bin/exiftool")
COORD_TOLERANCE = 0.0000005


def fail(message: str, exit_code: int = 1) -> int:
    logging.error(message)
    print(f"ERROR: {message}", file=sys.stderr)
    return exit_code


def load_config() -> dict[str, Any]:
    with CONFIG_PATH.open("r", encoding="utf-8") as handle:
        config = json.load(handle)
    if config.get("schema_version") != 1 or not isinstance(config.get("cameras"), list):
        raise ValueError("ugyldig kamerakonfigurasjon")
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


def camera_for_file(file_path: Path, config: dict[str, Any]) -> dict[str, Any] | None:
    relative = file_path.relative_to(ROOT)
    if len(relative.parts) < 2:
        return None
    camera_id = relative.parts[0]
    for camera in config["cameras"]:
        if camera.get("id") == camera_id:
            return camera
    return None


def read_metadata(
    file_path: Path,
) -> tuple[float | None, float | None, str, str, str, str, str]:
    command = [
        EXIFTOOL,
        "-charset",
        "IPTC=UTF8",
        "-n",
        "-T",
        "-GPSLatitude",
        "-GPSLongitude",
        "-IPTC:Sub-location",
        "-IPTC:Keywords",
        "-XMP-dc:Title",
        "-IPTC:Headline",
        "-IPTC:Caption-Abstract",
        "--",
        str(file_path),
    ]
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    values = result.stdout.rstrip("\r\n").split("\t")
    values += ["-"] * (7 - len(values))

    def coordinate(value: str) -> float | None:
        if value in ("", "-"):
            return None
        try:
            number = float(value)
        except ValueError:
            return None
        return number if math.isfinite(number) else None

    return (
        coordinate(values[0]),
        coordinate(values[1]),
        "" if values[2] == "-" else values[2],
        "" if values[3] == "-" else values[3],
        "" if values[4] == "-" else values[4],
        "" if values[5] == "-" else values[5],
        "" if values[6] == "-" else values[6],
    )


def metadata_matches(
    current: tuple[float | None, float | None, str, str, str, str, str],
    camera: dict[str, Any],
    managed_keywords: list[str],
) -> bool:
    (
        current_lat,
        current_lon,
        current_location,
        current_keywords,
        current_title,
        current_subject,
        current_comment,
    ) = current
    if current_lat is None or current_lon is None:
        return False
    if abs(current_lat - float(camera["latitude"])) >= COORD_TOLERANCE:
        return False
    if abs(current_lon - float(camera["longitude"])) >= COORD_TOLERANCE:
        return False
    if current_location != camera["location"] or current_title != camera["title"]:
        return False
    if current_subject != camera.get("subject", ""):
        return False
    if current_comment != camera.get("comment", ""):
        return False
    expected = {
        tag for tag in camera.get("tags", []) if isinstance(tag, str) and tag
    }
    if not all(keyword in current_keywords for keyword in expected):
        return False
    stale = set(managed_keywords) - expected
    return not any(keyword and keyword in current_keywords for keyword in stale)


def write_metadata(
    file_path: Path,
    camera: dict[str, Any],
    managed_keywords: list[str],
) -> None:
    camera_id = camera["id"]
    location = camera["location"]
    title = camera["title"]
    subject = camera.get("subject", "")
    comment = camera.get("comment", "")
    tags = [tag for tag in camera.get("tags", []) if isinstance(tag, str) and tag]
    command = [
        EXIFTOOL,
        "-quiet",
        "-quiet",
        "-P",
        "-overwrite_original_in_place",
        "-charset",
        "IPTC=UTF8",
        f"-GPSLatitude={camera['latitude']}",
        "-GPSLatitudeRef=N" if float(camera["latitude"]) >= 0 else "-GPSLatitudeRef=S",
        f"-GPSLongitude={camera['longitude']}",
        "-GPSLongitudeRef=E" if float(camera["longitude"]) >= 0 else "-GPSLongitudeRef=W",
        "-IPTC:CodedCharacterSet=UTF8",
        f"-IPTC:ObjectName={title}",
        f"-IPTC:Sub-location={location}",
        f"-IPTC:Headline={subject}",
        f"-XMP-photoshop:Headline={subject}",
        f"-IPTC:Caption-Abstract={comment}",
        f"-XMP-dc:Description={comment}",
    ]
    for keyword in dict.fromkeys(managed_keywords):
        command.extend(
            [f"-IPTC:Keywords-={keyword}", f"-XMP-dc:Subject-={keyword}"]
        )
    for tag in tags:
        command.extend([f"-IPTC:Keywords+={tag}", f"-XMP-dc:Subject+={tag}"])
    command.extend(
        [
            f"-XMP-iptcCore:Location={location}",
            f"-XMP-dc:Title={title}",
            "--",
            str(file_path),
        ]
    )
    subprocess.run(command, check=True)


def main(argv: list[str]) -> int:
    logging.basicConfig(level=logging.ERROR, format="%(message)s")
    if len(argv) != 2:
        return fail("Forventet nøyaktig én bildefil", 64)

    input_path = Path(argv[1])
    if not input_path.is_file() or input_path.is_symlink():
        return 0
    try:
        file_path = input_path.resolve(strict=True)
        file_path.relative_to(ROOT)
    except (OSError, ValueError):
        return 0
    if file_path.suffix.lower() not in (".jpg", ".jpeg"):
        return 0

    try:
        config = load_config()
        camera = camera_for_file(file_path, config)
        if camera is None or not camera.get("enabled", True):
            return 0
        managed_keywords = [
            value
            for value in config.get("managed_keywords", [])
            if isinstance(value, str) and value
        ]
        managed_keywords.extend(
            tag
            for tag in camera.get("tags", [])
            if isinstance(tag, str) and tag
        )
        current = read_metadata(file_path)
        if metadata_matches(current, camera, managed_keywords):
            return 0
        write_metadata(file_path, camera, managed_keywords)
    except (KeyError, TypeError, ValueError, OSError, subprocess.SubprocessError) as error:
        return fail(f"Kunne ikke behandle {file_path}: {error}")

    print(f"tagged\t{camera['id']}\t{file_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
