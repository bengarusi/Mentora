"""
AnswerValidationService — deterministic student-answer checking.

Validation priority:
  1. Both answers parse as Fraction → exact numeric comparison (highest confidence).
  2. SymPy symbolic equivalence (catches algebraic forms like x=2 vs 2).
  3. Case-insensitive string normalisation (last-resort, low confidence).

Returns a ToolResult; is_equivalent = None means "could not determine".
"""

from __future__ import annotations

import re

from app.math.normalizer import canonical_fraction_str, parse_to_fraction
from app.math.schemas import ToolResult
from app.math.sympy_service import SymPyMathService

_sympy_svc = SymPyMathService()


class AnswerValidationService:
    """Compare a student answer to the expected correct answer."""

    def validate(
        self,
        student_answer: str,
        correct_answer: str,
        allow_percentage_equivalent: bool = False,
    ) -> ToolResult:
        """
        Deterministically compare *student_answer* against *correct_answer*.

        Parameters
        ----------
        student_answer:
            Raw text submitted by the student.
        correct_answer:
            The canonical answer stored in the DB (possibly LLM-generated).
        allow_percentage_equivalent:
            If True, treat "50%" == "1/2" as correct.

        Returns
        -------
        ToolResult with:
          is_equivalent: True/False/None
          canonical_answer: normalised form of the correct answer
          tool_used: which method succeeded
        """
        student_clean = _clean(student_answer)
        correct_clean = _clean(correct_answer)

        # ---- 1. Fraction / numeric comparison --------------------------------
        student_frac = parse_to_fraction(student_clean)
        correct_frac = parse_to_fraction(correct_clean)

        if student_frac is not None and correct_frac is not None:
            canonical = canonical_fraction_str(correct_frac)
            return ToolResult(
                success=True,
                tool_used="fraction_arithmetic",
                canonical_answer=canonical,
                is_equivalent=(student_frac == correct_frac),
            )

        # ---- 2. Percentage ↔ fraction cross-check ----------------------------
        if allow_percentage_equivalent:
            # Try student as percentage vs correct as fraction (or vice-versa)
            student_pct_frac = _as_fraction_via_percentage(student_clean)
            if student_pct_frac is not None and correct_frac is not None:
                canonical = canonical_fraction_str(correct_frac)
                return ToolResult(
                    success=True,
                    tool_used="percentage_fraction_equivalence",
                    canonical_answer=canonical,
                    is_equivalent=(student_pct_frac == correct_frac),
                )

        # ---- 3. Equation-solving answer check --------------------------------
        # e.g. correct_answer is "2", student says "x = 2" or vice-versa
        student_rhs = _extract_rhs(student_clean)
        correct_rhs = _extract_rhs(correct_clean)
        if student_rhs and correct_rhs:
            sf = parse_to_fraction(student_rhs)
            cf = parse_to_fraction(correct_rhs)
            if sf is not None and cf is not None:
                canonical = canonical_fraction_str(cf)
                return ToolResult(
                    success=True,
                    tool_used="equation_answer_comparison",
                    canonical_answer=canonical,
                    is_equivalent=(sf == cf),
                )

        # ---- 4. SymPy symbolic equivalence -----------------------------------
        sympy_eq = _sympy_svc.are_equivalent(student_clean, correct_clean)
        if sympy_eq is not None:
            return ToolResult(
                success=True,
                tool_used="sympy_symbolic",
                canonical_answer=correct_clean,
                is_equivalent=sympy_eq,
            )

        # ---- 5. Normalised string fallback -----------------------------------
        # Only marks as equivalent for obvious trivial matches, not fractions
        if _normalise_str(student_clean) == _normalise_str(correct_clean):
            return ToolResult(
                success=True,
                tool_used="string_normalisation",
                canonical_answer=correct_clean,
                is_equivalent=True,
            )

        # ---- 6. Could not determine ------------------------------------------
        return ToolResult(
            success=False,
            tool_used="llm_fallback",
            canonical_answer=correct_clean,
            is_equivalent=None,
            warnings=["Could not parse answers numerically — LLM grading required"],
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean(text: str) -> str:
    return text.strip()


def _normalise_str(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _extract_rhs(text: str) -> str | None:
    """Return the RHS of 'var = value', or None if it's not in that form."""
    m = re.match(r"^[a-zA-Z]\s*=\s*(.+)$", text.strip())
    return m.group(1).strip() if m else None


def _as_fraction_via_percentage(text: str) -> object:
    """
    If *text* ends with '%' return it as a Fraction (e.g. "50%" → Fraction(1, 2)).
    Otherwise return None.  Relies on parse_to_fraction recognising the '%' suffix.
    """
    if text.endswith("%"):
        return parse_to_fraction(text)
    return None
