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
    # Free-form chat answer verification (teaching phase)
    # ------------------------------------------------------------------

    def verify_chat_answer(
        self, question_text: str, student_answer: str
    ) -> ToolResult:
        """
        Deterministically grade a free-form chat answer against an arithmetic
        question the tutor asked in prose, in English or Hebrew, e.g.
        "What is 3 times 6?", "כמה זה 12 חלקי 4?", "What is 25% of 40?".

        Covers the four operations, decimals, simple fractions and percentages.
        Skips classify() (the tutor's message is often several noisy sentences,
        which confuses the keyword classifier) and instead pulls the arithmetic
        expression straight out of the text and evaluates it exactly.

        Returns is_equivalent True/False only when it can SAFELY compute the
        answer. For anything else — non-numeric student answers, place-value /
        comparison / "which digit" style questions, or text with no extractable
        expression — it returns is_equivalent=None so the caller falls back to
        the LLM grader (never a guessed verdict).
        """
        none = ToolResult(success=False, tool_used="chat_arithmetic", is_equivalent=None)

        student_frac = parse_to_fraction(student_answer.strip())
        if student_frac is None:
            return none

        # Abstain on questions whose answer is NOT the value of the embedded
        # expression (e.g. "numerator of 3/4", "which is bigger 1/2 or 1/3",
        # place value). Computing those would produce a wrong verdict.
        if _has_non_computational_intent(question_text):
            return none

        expr = _extract_chat_expression(question_text)
        if expr is None:
            return none

        computed = _basic_calc.evaluate(expr)
        if computed is None:
            return none

        return ToolResult(
            success=True,
            tool_used="chat_arithmetic",
            canonical_answer=canonical_fraction_str(computed),
            is_equivalent=(student_frac == computed),
            steps_data=[
                f"extracted: {expr}",
                f"= {canonical_fraction_str(computed)}",
                f"student: {canonical_fraction_str(student_frac)}",
            ],
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

# Word/symbol forms of operators, so questions phrased in prose ("3 times 6",
# "3 כפול 6") are parseable. Longer phrases first so "multiplied by" wins over a
# bare "times". Covers English and Hebrew.
_WORD_OPERATORS = (
    (r"\bmultiplied\s+by\b", " * "),
    (r"\bdivided\s+by\b", " / "),
    (r"\btimes\b", " * "),
    (r"\bplus\b", " + "),
    (r"\bminus\b", " - "),
    # Hebrew
    (r"כפול", " * "),
    (r"מחולק\s*ב", " / "),
    (r"חלקי", " / "),
    (r"ועוד", " + "),
    (r"פלוס", " + "),
    (r"פחות", " - "),
    (r"מחוסר", " - "),
)

# Unicode math symbols → ASCII operators.
_SYMBOL_MAP = str.maketrans({"×": "*", "✕": "*", "·": "*", "∙": "*", "÷": "/", "−": "-"})

# Phrases meaning "percent of" → "/100*" so "25% of 40" becomes "25/100*40".
_PERCENT_OF = (
    r"%\s*of",
    r"percent\s*of",
    r"%\s*(?:מ-?|מתוך)",
    r"אחוז\s*(?:מ-?|מתוך)",
)

# Keywords whose answer is NOT the numeric value of an embedded expression.
# When present we abstain (return None) and let the LLM grade, so we never emit
# a wrong deterministic verdict. English + Hebrew.
_NON_COMPUTATIONAL_KEYWORDS = (
    "numerator", "denominator", "digit", "place value", "value of",
    "round", "nearest", "estimate",
    "bigger", "biggest", "smaller", "smallest", "greater", "greatest",
    "larger", "largest", "less than", "more than", "compare", "order",
    "arrange", "ascending", "descending", "between", "how many digits",
    "מונה", "מכנה", "ספרה", "ספרות", "ערך המקום", "ערך של", "עיגול",
    "עגל", "לעגל", "גדול", "קטן", "השווה", "השוו", "סדר", "סדרו",
    "אחדות", "עשרות", "מאות", "אלפים",
)


def _normalize_math_text(text: str) -> str:
    """Lowercase, map symbols/words to ASCII operators, expand "percent of"."""
    out = text.lower().translate(_SYMBOL_MAP)
    for pattern in _PERCENT_OF:
        out = re.sub(pattern, " /100* ", out)
    for pattern, symbol in _WORD_OPERATORS:
        out = re.sub(pattern, symbol, out)
    return out


def _has_non_computational_intent(text: str) -> bool:
    low = text.lower()
    return any(kw in low for kw in _NON_COMPUTATIONAL_KEYWORDS)


# A number is an integer, decimal, or fraction (a/b). Two or more numbers joined
# by + - * / form an expression. The LAST such expression in the text is taken —
# the asked question comes last, examples and intermediate steps come first.
_CHAT_EXPR_RE = re.compile(
    r"\d+(?:\.\d+)?(?:\s*/\s*\d+)?(?:\s*[+\-*/]\s*\d+(?:\.\d+)?(?:\s*/\s*\d+)?)+"
)


def _extract_chat_expression(text: str) -> str | None:
    normalized = _normalize_math_text(text)
    matches = _CHAT_EXPR_RE.findall(normalized)
    return matches[-1].strip() if matches else None


def _normalize_word_operators(text: str) -> str:
    out = text.lower()
    for pattern, symbol in _WORD_OPERATORS:
        out = re.sub(pattern, symbol, out)
    return out


def _extract_arithmetic_expression(text: str) -> str | None:
    """
    Extract a simple arithmetic expression from question text.
    e.g. "What is 2/5 + 1/10?" → "2/5 + 1/10", "What is 3 times 6?" → "3 * 6"

    When the text holds several expressions (e.g. a worked example followed by
    the question), the LAST one is returned — the asked question comes last,
    while examples and intermediate steps come first.
    """
    normalized = _normalize_word_operators(text)
    # Match expressions like "a/b + c/d", "3 * 4", "12 - 1/3 * 12", etc.
    pattern = re.compile(
        r"([\d]+(?:\s*/\s*[\d]+)?(?:\s*[\+\-\*]\s*[\d]+(?:\s*/\s*[\d]+)?)+)"
    )
    matches = pattern.findall(normalized)
    return matches[-1].strip() if matches else None


def _extract_equation(text: str) -> str | None:
    """
    Extract an equation like "2*x + 3 = 7" or "x + 5 = 12" from question text.
    """
    pattern = re.compile(
        r"([0-9a-z\s\+\-\*\/\^\(\)\.]+=[0-9a-z\s\+\-\*\/\^\(\)\.]+)",
        re.IGNORECASE,
    )
    match = pattern.search(text)
    if not match:
        return None
    equation = match.group(0).strip()
    # The permissive character class can include an instruction word before
    # the algebra. Remove common prose prefixes so SymPy sees one variable,
    # not the letters in "solve" as additional symbols.
    equation = re.sub(r"(?i)^(?:solve|find)\s+", "", equation)
    return equation
