"""
SymPyMathService — symbolic math using SymPy.

Provides:
  - symbolic expression equivalence checking
  - equation solving  (e.g. "2*x + 3 = 7" → x = 2)
  - algebraic simplification

SymPy is imported lazily; if it is not installed all methods return None
and the caller falls back to other tools or the LLM.
"""

from __future__ import annotations

import re
from fractions import Fraction

_sympy_available: bool | None = None


def _sympy():
    """Return sympy module or None if not installed."""
    global _sympy_available  # noqa: PLW0603
    if _sympy_available is None:
        try:
            import sympy  # noqa: F401

            _sympy_available = True
        except ImportError:
            _sympy_available = False
    if not _sympy_available:
        return None
    import sympy

    return sympy


class SymPyMathService:
    """Symbolic math operations via SymPy (optional dependency)."""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def are_equivalent(self, expr_a: str, expr_b: str) -> bool | None:
        """
        Return True if *expr_a* and *expr_b* are symbolically equivalent,
        False if they are definitively not, None if undetermined.
        """
        sp = _sympy()
        if sp is None:
            return None
        try:
            a = sp.sympify(expr_a, evaluate=True)
            b = sp.sympify(expr_b, evaluate=True)
            diff = sp.simplify(a - b)
            return bool(diff == 0)
        except Exception:
            return None

    def evaluate_expression(self, expr: str) -> Fraction | None:
        """
        Evaluate a symbolic expression and return an exact Fraction if possible.
        e.g. "2/5 + 1/10" → Fraction(1, 2)
        """
        sp = _sympy()
        if sp is None:
            return None
        try:
            result = sp.sympify(expr, evaluate=True)
            # Must be a rational number
            if result.is_number and result.is_rational:
                r = sp.Rational(result)
                return Fraction(int(r.p), int(r.q))
            return None
        except Exception:
            return None

    def solve_equation(self, equation_str: str, variable: str = "x") -> list[Fraction | str] | None:
        """
        Solve a one-variable equation string (e.g. "2*x + 3 = 7") for *variable*.
        Returns a list of solutions (may be Fraction or string for irrational),
        or None if SymPy is unavailable or parsing fails.
        """
        sp = _sympy()
        if sp is None:
            return None
        try:
            var = sp.Symbol(variable)
            lhs_str, rhs_str = _split_equation(equation_str)
            if lhs_str is None:
                return None
            lhs = sp.sympify(lhs_str, locals={variable: var}, evaluate=True)
            rhs = sp.sympify(rhs_str, locals={variable: var}, evaluate=True)
            solutions = sp.solve(lhs - rhs, var)
            result = []
            for sol in solutions:
                if sol.is_rational:
                    r = sp.Rational(sol)
                    result.append(Fraction(int(r.p), int(r.q)))
                else:
                    result.append(str(sol))
            return result
        except Exception:
            return None

    def simplify_expression(self, expr: str) -> str | None:
        """Return a simplified string form, or None on failure."""
        sp = _sympy()
        if sp is None:
            return None
        try:
            result = sp.simplify(sp.sympify(expr, evaluate=True))
            return str(result)
        except Exception:
            return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _split_equation(equation_str: str) -> tuple[str | None, str | None]:
    """Split 'lhs = rhs' into two parts.  Returns (None, None) on failure."""
    parts = equation_str.split("=")
    if len(parts) != 2:
        return None, None
    return parts[0].strip(), parts[1].strip()
