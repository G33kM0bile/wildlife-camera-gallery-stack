#!/usr/bin/env python3
"""Validate completed wildlife-camera MP4 uploads and quarantine bad files."""

from __future__ import annotations

import argparse
import logging
import os
import queue
import shutil
import subprocess
import threading
import time
from pathlib import Path

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer


WATCH_ROOT = Path(os.environ.get("WATCH_ROOT", "/srv/sftpgo/data"))
QUARANTINE_ROOT = Path(
    os.environ.get("QUARANTINE_ROOT", "/srv/sftpgo/quarantine")
)
CAMERAS = tuple(f"hc960-{number:02d}" for number in range(1, 6))
RETRIES = int(os.environ.get("RETRIES", "3"))
RETRY_DELAY = float(os.environ.get("RETRY_DELAY", "15"))
PROCESS_DELAY = float(os.environ.get("PROCESS_DELAY", "5"))
FFPROBE_TIMEOUT = float(os.environ.get("FFPROBE_TIMEOUT", "120"))

LOG = logging.getLogger("wildlife-video-validator")


def camera_for(path: Path) -> str | None:
    """Return the camera folder for a safe MP4 below WATCH_ROOT."""
    try:
        relative = path.resolve(strict=False).relative_to(WATCH_ROOT.resolve())
    except ValueError:
        return None
    if len(relative.parts) < 2 or relative.parts[0] not in CAMERAS:
        return None
    if path.suffix.lower() != ".mp4":
        return None
    return relative.parts[0]


def valid_video(path: Path) -> bool:
    """Return true when ffprobe can parse the MP4 without errors."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "--", str(path)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=FFPROBE_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        LOG.warning("ffprobe failed file=%s error=%s", path, error)
        return False
    return result.returncode == 0


def quarantine_destination(camera: str, source: Path) -> Path:
    directory = QUARANTINE_ROOT / camera
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / source.name
    if not destination.exists():
        return destination

    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    counter = 1
    while True:
        candidate = directory / f"{source.stem}.{stamp}.{counter}{source.suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def validate(path: Path, *, initial_delay: bool = True) -> bool:
    """Validate one upload. Return true if it remains in the gallery tree."""
    camera = camera_for(path)
    if camera is None or not path.is_file():
        return True

    if initial_delay:
        time.sleep(PROCESS_DELAY)
    if not path.is_file():
        return True

    for attempt in range(1, RETRIES + 1):
        if valid_video(path):
            LOG.info("VALID camera=%s file=%s", camera, path)
            return True
        LOG.warning(
            "INVALID attempt=%d/%d camera=%s file=%s",
            attempt,
            RETRIES,
            camera,
            path,
        )
        if attempt < RETRIES:
            time.sleep(RETRY_DELAY)
            if not path.is_file():
                return True

    destination = quarantine_destination(camera, path)
    shutil.move(str(path), str(destination))
    LOG.error(
        "QUARANTINED camera=%s source=%s destination=%s",
        camera,
        path,
        destination,
    )
    return False


class VideoQueue:
    """Serialize validation and coalesce duplicate filesystem events."""

    def __init__(self) -> None:
        self.items: queue.Queue[Path | None] = queue.Queue()
        self.pending: set[Path] = set()
        self.lock = threading.Lock()
        self.worker = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self.worker.start()

    def submit(self, path: Path) -> None:
        path = path.resolve(strict=False)
        if camera_for(path) is None:
            return
        with self.lock:
            if path in self.pending:
                return
            self.pending.add(path)
        self.items.put(path)

    def stop(self) -> None:
        self.items.put(None)
        self.worker.join(timeout=FFPROBE_TIMEOUT + RETRIES * RETRY_DELAY + 10)

    def _run(self) -> None:
        while True:
            path = self.items.get()
            if path is None:
                self.items.task_done()
                return
            try:
                validate(path)
            except Exception:
                LOG.exception("Unhandled validation error file=%s", path)
            finally:
                with self.lock:
                    self.pending.discard(path)
                self.items.task_done()


class UploadHandler(FileSystemEventHandler):
    def __init__(self, videos: VideoQueue) -> None:
        self.videos = videos

    def on_closed(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self.videos.submit(Path(event.src_path))

    def on_moved(self, event: FileSystemEvent) -> None:
        if not event.is_directory and getattr(event, "dest_path", None):
            self.videos.submit(Path(event.dest_path))


def scan() -> int:
    total = 0
    broken = 0
    for camera in CAMERAS:
        directory = WATCH_ROOT / camera
        if not directory.is_dir():
            continue
        for path in sorted(directory.rglob("*")):
            if not path.is_file() or path.suffix.lower() != ".mp4":
                continue
            total += 1
            if not validate(path, initial_delay=False):
                broken += 1
    LOG.info("Existing scan complete total=%d broken=%d", total, broken)
    return broken


def watch() -> None:
    videos = VideoQueue()
    videos.start()
    observer = Observer()
    observer.schedule(UploadHandler(videos), str(WATCH_ROOT), recursive=True)
    observer.start()
    LOG.info("Watching %s for completed MP4 uploads", WATCH_ROOT)
    try:
        while observer.is_alive():
            observer.join(timeout=1)
    except KeyboardInterrupt:
        LOG.info("Stopping")
    finally:
        observer.stop()
        observer.join()
        videos.stop()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scan",
        action="store_true",
        help="scan existing MP4 files once instead of watching uploads",
    )
    args = parser.parse_args()
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(message)s",
    )

    if not WATCH_ROOT.is_dir():
        parser.error(f"watch root does not exist: {WATCH_ROOT}")
    for camera in CAMERAS:
        (QUARANTINE_ROOT / camera).mkdir(parents=True, exist_ok=True)

    if args.scan:
        scan()
        return 0
    watch()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
