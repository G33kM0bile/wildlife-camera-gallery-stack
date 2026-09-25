#!/usr/bin/env python3
"""Install the tested temperature parser into the live monolithic watcher."""

from __future__ import annotations

import shutil
from pathlib import Path


WATCHER = Path("/opt/wildlife-ocr/wildlife_ocr_watcher.py")
BACKUP = WATCHER.with_suffix(".py.before-temperature-parser")

IMPORT_ANCHOR = "from watchdog.observers import Observer\n"
IMPORT_LINE = "from temperature_parser import parse_temperature_pair\n"

OLD_BLOCK = '''    temperature_match = TEMP_RE.search(text)

    if temperature_match:
        temperature_c = int(temperature_match.group(1))
        temperature_f = int(temperature_match.group(2))

        if -50 <= temperature_c <= 70:
            result["temperature_c"] = temperature_c

        if -60 <= temperature_f <= 160:
            result["temperature_f"] = temperature_f
'''

NEW_BLOCK = '''    temperature_pair = parse_temperature_pair(
        text,
        start=date_match.end() if date_match else 0,
    )

    if temperature_pair:
        result["temperature_c"], result["temperature_f"] = temperature_pair
'''


def main() -> int:
    source = WATCHER.read_text()

    if IMPORT_LINE in source and NEW_BLOCK in source:
        print("Temperature parser is already installed")
        return 0

    if IMPORT_ANCHOR not in source or OLD_BLOCK not in source:
        raise SystemExit("Watcher source differs from the expected version; not modifying it")

    if not BACKUP.exists():
        shutil.copy2(WATCHER, BACKUP)

    source = source.replace(IMPORT_ANCHOR, IMPORT_ANCHOR + IMPORT_LINE, 1)
    source = source.replace(OLD_BLOCK, NEW_BLOCK, 1)
    WATCHER.write_text(source)
    print(f"Installed temperature parser; backup: {BACKUP}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
