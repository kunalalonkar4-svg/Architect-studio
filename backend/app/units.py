"""Unit normalisation. All geometry is stored in millimetres.

Handles feet-inches (30'6", 30 ft 6 in), decimal feet, metres, centimetres, millimetres,
including common Hindi/Hinglish spellings. Never guesses a unit: bare numbers raise AmbiguousUnit.
"""
from __future__ import annotations

import re

MM_PER = {"mm": 1.0, "cm": 10.0, "m": 1000.0, "ft": 304.8, "in": 25.4}


class AmbiguousUnit(ValueError):
    """Raised when a number has no unit (or an unknown one). Callers must ask the user."""

    def __init__(self, message: str, raw: str | None = None):
        super().__init__(message)
        self.raw = raw


_UNIT_ALIASES = {
    "mm": "mm", "millimetre": "mm", "millimeter": "mm", "millimetres": "mm", "millimeters": "mm",
    "cm": "cm", "centimetre": "cm", "centimeter": "cm", "centimetres": "cm", "centimeters": "cm",
    "m": "m", "mtr": "m", "mtrs": "m", "meter": "m", "metre": "m", "meters": "m", "metres": "m", "मीटर": "m",
    "ft": "ft", "feet": "ft", "foot": "ft", "fit": "ft", "fut": "ft", "फुट": "ft", "फीट": "ft", "'": "ft", "’": "ft",
    "in": "in", "inch": "in", "inches": "in", "इंच": "in", '"': "in", "”": "in", "''": "in",
}


def canonical_unit(unit: str | None) -> str:
    if unit is None:
        raise AmbiguousUnit("No unit given")
    u = unit.strip().lower().rstrip(".")
    if u in ("", "unspecified", "unknown", "none"):
        raise AmbiguousUnit("No unit given")
    if u not in _UNIT_ALIASES:
        raise AmbiguousUnit(f"Unknown unit '{unit}'")
    return _UNIT_ALIASES[u]


def to_mm(value: float, unit: str | None) -> float:
    """Convert a value to millimetres. Raises AmbiguousUnit for missing/unknown units."""
    return round(float(value) * MM_PER[canonical_unit(unit)], 3)


_NUM = r"(\d+(?:\.\d+)?)"
_UNIT_RE = r"(mm|cm|metres?|meters?|mtrs?|m|feet|foot|ft|fit|fut|फुट|फीट|inches|inch|in|इंच)"


def parse_length(text: str) -> float:
    """Parse one length such as "30 ft 6 in", "30'6\"", "9.5 m", "9000mm" -> mm."""
    t = text.strip().lower().replace("’", "'").replace("”", '"')
    m = re.fullmatch(rf"{_NUM}\s*'\s*(?:{_NUM}\s*(?:\"|''|in|inch|inches)?)?", t)
    if m:
        ft = float(m.group(1))
        inch = float(m.group(2)) if m.group(2) else 0.0
        return round(ft * 304.8 + inch * 25.4, 3)
    m = re.fullmatch(rf"{_NUM}\s*(?:ft|feet|foot|फुट|फीट)\s*(?:{_NUM}\s*(?:in|inch|inches|इंच)?)?", t)
    if m:
        ft = float(m.group(1))
        inch = float(m.group(2)) if m.group(2) else 0.0
        return round(ft * 304.8 + inch * 25.4, 3)
    m = re.fullmatch(rf"{_NUM}\s*{_UNIT_RE}", t)
    if m:
        return to_mm(float(m.group(1)), m.group(2))
    raise AmbiguousUnit(f"Cannot read a length with a clear unit from '{text}'", raw=text)


def parse_plot_dims(text: str) -> tuple[float, float] | None:
    """Parse "30 by 50 feet", "30x50 ft", "30 ft x 50 ft", "9 m by 15 m" -> (a_mm, b_mm).

    Returns None if no pair is present. Raises AmbiguousUnit if a pair has no unit.
    """
    t = text.lower().replace("×", "x").replace("*", "x")
    sep = r"(?:x|by|bai|baai|ke\s+bajaye)"
    m = re.search(rf"{_NUM}\s*{_UNIT_RE}?\s*{sep}\s*{_NUM}\s*{_UNIT_RE}?", t)
    if not m:
        m2 = re.search(rf"{_NUM}\s*'\s*x\s*{_NUM}\s*'", t)
        if m2:
            return round(float(m2.group(1)) * 304.8, 3), round(float(m2.group(2)) * 304.8, 3)
        return None
    a, ua, b, ub = m.group(1), m.group(2), m.group(3), m.group(4)
    unit = ub or ua
    if unit is None:
        raise AmbiguousUnit(f"'{a} by {b}' has no unit (feet? metres?)", raw=m.group(0))
    return to_mm(float(a), ua or unit), to_mm(float(b), unit)


def fmt_ft_in(mm: float) -> str:
    total_in = mm / 25.4
    feet = int(total_in // 12)
    inch = total_in - feet * 12
    if round(inch, 1) >= 12:
        feet, inch = feet + 1, 0
    return f"{feet}'-{inch:.0f}\"" if abs(inch - round(inch)) < 0.05 else f"{feet}'-{inch:.1f}\""
