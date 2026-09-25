"""Robust parsing of the dual Celsius/Fahrenheit Suntek footer value."""

from __future__ import annotations

import re


TEMPERATURE_PAIR_RE = re.compile(
    r"(?<![\d/])(-?\d{1,3})\s*[^0-9/\s]{0,4}\s*/\s*"
    r"(-?\d{1,3})(?!\d)",
    re.IGNORECASE,
)

MAX_FAHRENHEIT_ERROR = 4.0


def _number_candidates(token: str) -> list[int]:
    """Return the OCR number and a variant without a trailing glyph digit."""
    sign = -1 if token.startswith("-") else 1
    digits = token.lstrip("-")
    values = [sign * int(digits)]

    # Tesseract regularly reads the tiny degree/C/F glyph as a final 7 or 5:
    # 6°C/42°F -> 67/42 and 9°C/48°F -> 9/485.
    if len(digits) >= 2:
        shortened = sign * int(digits[:-1])
        if shortened not in values:
            values.append(shortened)

    return values


def parse_temperature_pair(
    text: str,
    *,
    start: int = 0,
) -> tuple[int, int] | None:
    """
    Parse the camera's ``C/F`` pair without requiring degree or unit glyphs.

    Both values must agree with the Celsius/Fahrenheit conversion. This rejects
    spikes such as ``67/42`` and repairs common OCR output such as ``87/46 F``.
    ``start`` can be set to the end of the timestamp to avoid matching date
    components in unusual footer text.
    """
    best: tuple[float, int, int] | None = None

    for match in TEMPERATURE_PAIR_RE.finditer(text, pos=max(0, start)):
        for celsius in _number_candidates(match.group(1)):
            if not -50 <= celsius <= 70:
                continue

            for fahrenheit in _number_candidates(match.group(2)):
                if not -60 <= fahrenheit <= 160:
                    continue

                error = abs(fahrenheit - (celsius * 9 / 5 + 32))

                if error > MAX_FAHRENHEIT_ERROR:
                    continue

                candidate = (error, celsius, fahrenheit)
                if best is None or candidate < best:
                    best = candidate

    if best is None:
        return None

    return best[1], best[2]
