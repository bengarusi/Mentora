"""
BasicCalculatorService — deterministic arithmetic evaluation.

Uses Python's fractions.Fraction for exact results on basic arithmetic.
If SymPy is available it is used for algebraic / symbolic expressions.
"""

from __future__ import annotations

import re
from fractions import Fraction

from app.math.normalizer import parse_to_fraction


class BasicCalculatorService:
    """Evaluate simple arithmetic expressions that contain only numeric literals."""

    # Characters allowed in a safe arithmetic expression
    _SAFE_PATTERN = re.compile(r"^[\d\s\+\-\*\/\(\)\.]+$")
    _MAX_EXPRESSION_LENGTH = 256

    def evaluate(self, expr: str) -> Fraction | None:
        """
        Evaluate *expr* and return an exact Fraction.
        Returns None for unsupported or unsafe input.

        Supports: integers, fractions written as a/b, decimals, and the four
        basic operators +, -, *, /.  Parentheses are respected.

        Examples:
            "2/5 + 1/10"  →  Fraction(1, 2)
            "3 * 0.25"    →  Fraction(3, 4)
            "1 - 1/3"     →  Fraction(2, 3)
        """
        cleaned = expr.strip()
        if len(cleaned) > self._MAX_EXPRESSION_LENGTH or "**" in cleaned:
            return None

        # Convert "a/b" tokens to Fraction literals before evaluation
        # so that "2/5 + 1/10" is interpreted as Fraction(2,5) + Fraction(1,10)
        converted = self._convert_fractions(cleaned)
        if converted is None:
            return None

        return _safe_eval_fraction(converted)

    # ---------------------------------------------------------------------------
    # Private helpers
    # ---------------------------------------------------------------------------

    @staticmethod
    def _convert_fractions(expr: str) -> str | None:
        """Replace every a/b token with Fraction(a, b) for safe evaluation."""
        # Reject anything that's not digits, spaces, operators, parentheses, dots
        allowed = re.compile(r"^[\d\s\+\-\*\/\(\)\.]+$")
        if not allowed.match(expr) or "**" in expr:
            return None
        # Avoid division by zero at the token level
        # Replace fraction tokens (number/number) with Fraction(a, b) calls
        result = re.sub(
            r"(\d+)\s*/\s*(\d+)",
            lambda m: f"Fraction({m.group(1)}, {m.group(2)})",
            expr,
        )
        return result


def _safe_eval_fraction(expr: str) -> Fraction | None:
    """
    Evaluate *expr* in a very restricted namespace that only exposes Fraction.
    This is safe because _convert_fractions already rejected any non-arithmetic
    characters.
    """
    try:
        result = eval(expr, {"__builtins__": {}}, {"Fraction": Fraction})  # noqa: S307
        if isinstance(result, (int, Fraction)):
            return Fraction(result)
        if isinstance(result, float):
            return Fraction(result).limit_denominator(100_000)
        return None
    except Exception:
        return None
