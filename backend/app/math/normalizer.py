"""
Converts student and system answers into a canonical Python Fraction.

Supported input formats:
  - integers          "3"
  - fractions         "1/2", "3/4"
  - mixed numbers     "1 1/2"  (returns 3/2)
  - decimals          "0.5", "1.25"
  - percentages       "50%"
  - equation answers  "x = 2", "x=2"  (extracts the RHS if it is numeric)
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from fractions import Fraction


def parse_to_fraction(text: str) -> Fraction | None:
    """
    Try to parse *text* into a Fraction.
    Returns None if the text is not parseable as a numeric value.
    Never raises.
    """
    if not isinstance(text, str):
        return None

    t = text.strip()

    # Strip equation prefix: "x = 2" → "2"
    eq_match = re.match(r"^[a-zA-Z]\s*=\s*(.+)$", t)
    if eq_match:
        t = eq_match.group(1).strip()

    # Percentage: "50%" → 1/2
    if t.endswith("%"):
        return _parse_percentage(t[:-1].strip())

    # Mixed number: "1 1/2"
    mixed = re.match(r"^(-?\d+)\s+(\d+)\s*/\s*(\d+)$", t)
    if mixed:
        whole = int(mixed.group(1))
        num = int(mixed.group(2))
        den = int(mixed.group(3))
        if den == 0:
            return None
        sign = -1 if whole < 0 else 1
        return Fraction(abs(whole) * den + num, den) * sign

    # Plain fraction: "1/2", "-3/4"
    if "/" in t:
        parts = t.split("/")
        if len(parts) == 2:
            try:
                return Fraction(int(parts[0].strip()), int(parts[1].strip()))
            except (ValueError, ZeroDivisionError):
                return None

    # Decimal: "0.5"
    try:
        return Fraction(Decimal(t)).limit_denominator(100_000)
    except (InvalidOperation, ValueError):
        pass

    # Integer: "2"
    try:
        return Fraction(int(t))
    except ValueError:
        return None


def canonical_fraction_str(frac: Fraction) -> str:
    """Return a human-readable canonical string for a fraction (e.g. "1/2" or "3")."""
    if frac.denominator == 1:
        return str(frac.numerator)
    return f"{frac.numerator}/{frac.denominator}"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_percentage(num_str: str) -> Fraction | None:
    try:
        val = Decimal(num_str) / Decimal("100")
        return Fraction(val).limit_denominator(100_000)
    except (InvalidOperation, ValueError):
        return None
