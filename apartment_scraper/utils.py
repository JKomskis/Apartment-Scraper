"""Small parsing helpers shared across spiders.

Apartment sites format prices and sizes in many ways ("$1,250/mo", "1,024 sq ft").
These helpers pull a clean number out of that text.
"""

from __future__ import annotations

import re

_NUMBER_RE = re.compile(r"[-+]?\d*\.?\d+")


def to_float(value: str | None) -> float | None:
    """Return the first number in ``value`` as a float.

    >>> to_float("$1,250/mo")
    1250.0
    >>> to_float(None) is None
    True
    """
    if value is None:
        return None
    match = _NUMBER_RE.search(value.replace(",", ""))
    return float(match.group()) if match else None


def to_int(value: str | None) -> int | None:
    """Return the first number in ``value`` as an int.

    >>> to_int("1,024 sq ft")
    1024
    """
    number = to_float(value)
    return int(number) if number is not None else None


def _as_float(value: str | float | int | None) -> float | None:
    """Coerce text or a raw number to a float, or ``None``."""
    if value is None:
        return None
    return to_float(value) if isinstance(value, str) else float(value)


def to_whole_number(value: str | float | int | None) -> int | None:
    """Return ``value`` rounded to the nearest whole number, as an int.

    Accepts raw numbers as well as text to pull a number out of. Useful for
    counts (like bedrooms) that should always be a whole number.

    >>> to_whole_number("2 Bed")
    2
    >>> to_whole_number(1.5)
    2
    """
    number = _as_float(value)
    return round(number) if number is not None else None


def to_number(value: str | float | int | None) -> int | float | None:
    """Return ``value`` as an int when it's a whole number, a float otherwise.

    Accepts raw numbers as well as text to pull a number out of. Useful for
    counts (like bathrooms) where a half-value (e.g. 1.5) is meaningful but a
    whole value should be a plain int rather than e.g. ``2.0``.

    >>> to_number("1.5 Bath")
    1.5
    >>> to_number("2 Bath")
    2
    >>> to_number(2.0)
    2
    """
    number = _as_float(value)
    if number is None:
        return None
    return int(number) if number.is_integer() else number
