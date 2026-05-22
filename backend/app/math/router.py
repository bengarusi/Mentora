"""
MathRouterService — classifies math problems and orchestrates tools.

Classification:
  basic_arithmetic     — plain integer / decimal operations
  fraction_arithmetic  — fractions (answer contains '/', typical for primary maths)
  percentage           — percentage results or inputs
  equation_solving     — equations with a variable ("2*x + 3 = 7")
  algebra_simplification — simplify / factor / expand expressions
  geometry_formula     — named formula (area, volume, Pythagoras, …)
  word_problem         — word problem requiring semantic extraction
  unsupported          — cannot be handled deterministically

For the first implementation MathRouterService focuses on answer validation
(which tool to use to compare student answer with correct answer) and
correct-answer verification (can we compute the answer from the expression
embedded in the question / the stored correct_answer).
"""

from __future__ import annotations

import re

from app.math.calculator import BasicCalculatorService
from app.math.normalizer import canonical_fraction_str, parse_to_fraction
from app.math.schemas import ToolResult
from app.math.sympy_service import SymPyMathService
from app.math.validator import AnswerValidationService

_basic_calc = BasicCalculatorService()
_sympy_svc = SymPyMathService()
_validator = AnswerValidationService()


class MathType:
    BASIC_ARITHMETIC = "basic_arithmetic"
    FRACTION_ARITHMETIC = "fraction_arithmetic"
    DECIMAL_ARITHMETIC = "decimal_arithmetic"
    PERCENTAGE = "percentage"
    EQUATION_SOLVING = "equation_solving"
    ALGEBRA_SIMPLIFICATION = "algebra_simplification"
    GEOMETRY_FORMULA = "geometry_formula"
    WORD_PROBLEM = "word_problem"
    UNSUPPORTED = "unsupported"


class MathRouterService:
    """Decide which tool to use, then call it."""

    # ------------------------------------------------------------------
    # Classification
    # ------------------------------------------------------------------

    def classify(self, question_text: str, correct_answer: str) -> str:
        """Return a MathType constant for the given question / answer pair."""
        q = question_text.lower()
        a = correct_answer.strip().lower()

        # Equation: question or answer contains '=' with a variable
        if re.search(r"[a-z]\s*=|\bsolve\b|\bfind\b.*[a-z]\b", q):
            return MathType.EQUATION_SOLVING

        # Fraction answer or fraction arithmetic in question
        if "/" in a or re.search(r"\d+\s*/\s*\d+", q):
            return MathType.FRACTION_ARITHMETIC

        # Percentage
        if "%" in a or "percent" in q:
            return MathType.PERCENTAGE

        # Decimal answer
        if re.search(r"\d+\.\d+", a):
            return MathType.DECIMAL_ARITHMETIC

        # Algebra: variable in expression but no "="
        if re.search(r"simplif|factor|expand|express", q):
            return MathType.ALGEBRA_SIMPLIFICATION

        # Geometry keywords
        geo_kw = (
            "area", "perimeter", "volume", "circumference",
            "hypotenuse", "radius", "diameter", "triangle",
            "rectangle", "circle", "square", "cube", "cylinder",
        )
        if any(kw in q for kw in geo_kw):
            return MathType.GEOMETRY_FORMULA

        # Word problem heuristic (contains names, units, or story words)
        wp_kw = (
            "how many", "how much", "apples", "oranges", "cookies",
            "students", "metres", "liters", "dollars", "minutes",
        )
        if any(kw in q for kw in wp_kw):
            return MathType.WORD_PROBLEM

        # Plain integer arithmetic
        if re.match(r"^-?\d+$", a):
            return MathType.BASIC_ARITHMETIC

        return MathType.UNSUPPORTED

    # ------------------------------------------------------------------
    # Answer validation entry-point
    # ------------------------------------------------------------------

    def validate_student_answer(
        self,
        question_text: str,
        correct_answer: str,
        student_answer: str,
    ) -> ToolResult:
        """
        Main entry-point for grading a student answer.
        Returns ToolResult; is_equivalent=None means fall back to LLM.
        """
        math_type = self.classify(question_text, correct_answer)
        allow_pct = math_type == MathType.PERCENTAGE

        return _validator.validate(
            student_answer,
            correct_answer,
            allow_percentage_equivalent=allow_pct,
        )

    # ------------------------------------------------------------------
    # Question-answer verification (during question generation)
    # ------------------------------------------------------------------

    def try_compute_correct_answer(
        self, question_text: str, llm_correct_answer: str
    ) -> ToolResult:
        """
        Try to independently compute the answer to *question_text*.
        Returns ToolResult with canonical_answer if successful.

        This is a best-effort check: many question types (word problems,
        multi-step algebra) can't be solved from the text alone.
        When possible, compares the computed answer to the LLM-provided one
        and sets is_equivalent accordingly.
        """
        math_type = self.classify(question_text, llm_correct_answer)

        # ---- Fraction / decimal arithmetic --------------------------------
        if math_type in (
            MathType.FRACTION_ARITHMETIC,
            MathType.DECIMAL_ARITHMETIC,
            MathType.BASIC_ARITHMETIC,
        ):
            expr = _extract_arithmetic_expression(question_text)
            if expr:
                computed = _basic_calc.evaluate(expr)
                if computed is not None:
                    canonical = canonical_fraction_str(computed)
                    llm_frac = parse_to_fraction(llm_correct_answer)
                    if llm_frac is not None:
                        match = computed == llm_frac
                    else:
                        match = None
                    return ToolResult(
                        success=True,
                        tool_used=math_type,
                        canonical_answer=canonical,
                        is_equivalent=match,
                        warnings=(
                            [f"LLM answer '{llm_correct_answer}' disagrees with computed '{canonical}'"]
                            if match is False
                            else []
                        ),
                    )

        # ---- Equation solving -----------------------------------------------
        if math_type == MathType.EQUATION_SOLVING:
            eq = _extract_equation(question_text)
            if eq:
                solutions = _sympy_svc.solve_equation(eq)
                if solutions and len(solutions) == 1:
                    sol = solutions[0]
                    canonical = str(sol)
                    llm_frac = parse_to_fraction(llm_correct_answer)
                    computed_frac = sol if isinstance(sol, object) else None
                    from fractions import Fraction
                    if isinstance(sol, Fraction) and llm_frac is not None:
                        match = sol == llm_frac
                    else:
                        match = None
                    return ToolResult(
                        success=True,
                        tool_used="sympy_equation",
                        canonical_answer=canonical,
                        is_equivalent=match,
                    )

        # ---- Fall through — unsupported for this question type ---------------
        return ToolResult(
            success=False,
            tool_used="unsupported",
            canonical_answer=llm_correct_answer,
            is_equivalent=None,
            warnings=[f"Question type '{math_type}' not supported for answer verification"],
        )


# ---------------------------------------------------------------------------
# Expression / equation extraction helpers
# ---------------------------------------------------------------------------

def _extract_arithmetic_expression(text: str) -> str | None:
    """
    Extract a simple arithmetic expression from question text.
    e.g. "What is 2/5 + 1/10?" → "2/5 + 1/10"
    """
    # Match expressions like "a/b + c/d", "3 * 4", "12 - 1/3 * 12", etc.
    pattern = re.compile(
        r"([\d]+(?:\s*/\s*[\d]+)?(?:\s*[\+\-\*]\s*[\d]+(?:\s*/\s*[\d]+)?)+)"
    )
    match = pattern.search(text)
    return match.group(0).strip() if match else None


def _extract_equation(text: str) -> str | None:
    """
    Extract an equation like "2*x + 3 = 7" or "x + 5 = 12" from question text.
    """
    pattern = re.compile(
        r"([0-9a-z\s\+\-\*\/\^\(\)\.]+=[0-9a-z\s\+\-\*\/\^\(\)\.]+)"
    )
    match = pattern.search(text, re.IGNORECASE)
    return match.group(0).strip() if match else None
