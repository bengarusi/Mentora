from __future__ import annotations

import re
from collections.abc import Sequence
from fractions import Fraction
from typing import Protocol

from app.agent.schemas import EvaluationResult, HomeworkExercise
from app.llm.provider import LLMError
from app.math.normalizer import canonical_fraction_str, parse_to_fraction
from app.math.router import MathRouterService
from app.math.sympy_service import SymPyMathService

_NUMERIC_CANDIDATE = re.compile(
    r"(?<![\w/])-?\d+(?:\s+\d+\s*/\s*\d+|\s*/\s*\d+|\.\d+|%)?(?![\w/])"
)
_TERMINAL_RESULT_CLAUSE = re.compile(
    rf"(?:\bis\b|\bequals?\b|=)\s*(?P<value>{_NUMERIC_CANDIDATE.pattern})"
    r"\s*[.!?]?\s*$",
    re.IGNORECASE,
)


class ChatGrader(Protocol):
    def grade_chat_answer(self, question_text: str, student_answer: str): ...


def _numeric_candidates(text: str) -> tuple[str, ...]:
    direct = parse_to_fraction(text)
    if direct is not None:
        return (canonical_fraction_str(direct),)
    candidates: list[str] = []
    matches = _NUMERIC_CANDIDATE.findall(text)
    for value in matches:
        parsed = parse_to_fraction(value)
        if parsed is not None:
            canonical = canonical_fraction_str(parsed)
            if canonical not in candidates:
                candidates.append(canonical)
    return tuple(candidates)


_SPOKEN_UNITS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
    "seventeen": 17, "eighteen": 18, "nineteen": 19,
}
_SPOKEN_TENS = {
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}
_SPOKEN_DENOMINATORS = {
    "half": 2, "halves": 2, "third": 3, "thirds": 3, "quarter": 4,
    "quarters": 4, "fourth": 4, "fourths": 4, "fifth": 5, "fifths": 5,
    "sixth": 6, "sixths": 6, "seventh": 7, "sevenths": 7, "eighth": 8,
    "eighths": 8, "ninth": 9, "ninths": 9, "tenth": 10, "tenths": 10,
}
#: Words a student wraps an answer in. Dropped before the number is read.
_SPOKEN_FILLER = frozenset(
    {"the", "answer", "is", "it", "its", "i", "think", "equals", "equal", "to",
     "that", "would", "be", "so", "um", "uh", "well", "maybe"}
)
_SPOKEN_WORD = re.compile(r"[a-z']+")


def _spoken_number_candidate(text: str) -> str | None:
    """A number said in words — "three quarters", "seven" — as a canonical value.

    Speech is how this arrives: transcription writes fractions as words, so
    without this a student who says the right answer aloud is never credited
    with it. Kept deliberately strict — after the filler words are dropped, what
    is left must be nothing but the number — so "one more time" is not read as
    the answer 1.
    """
    tokens = [
        token
        for token in _SPOKEN_WORD.findall(text.lower().replace("-", " "))
        if token not in _SPOKEN_FILLER
    ]
    if not tokens:
        return None

    sign = 1
    whole = 0
    denominator: int | None = None
    saw_number = False
    for token in tokens:
        if token in ("negative", "minus"):
            sign = -1
        elif token in ("a", "an", "and"):
            continue
        elif token == "hundred":
            whole = (whole or 1) * 100
            saw_number = True
        elif token in _SPOKEN_UNITS:
            whole += _SPOKEN_UNITS[token]
            saw_number = True
        elif token in _SPOKEN_TENS:
            whole += _SPOKEN_TENS[token]
            saw_number = True
        elif token in _SPOKEN_DENOMINATORS and denominator is None:
            denominator = _SPOKEN_DENOMINATORS[token]
        else:
            return None  # a word we do not understand: this is not a number

    if denominator is None and not saw_number:
        return None
    numerator = whole if saw_number else 1  # "a half"
    return canonical_fraction_str(Fraction(sign * numerator, denominator or 1))


def _terminal_result_candidate(text: str) -> str | None:
    match = _TERMINAL_RESULT_CLAUSE.search(text)
    if match is None:
        return None
    parsed = parse_to_fraction(match.group("value"))
    return canonical_fraction_str(parsed) if parsed is not None else None


class AnswerEvaluator:
    """Resolve a server-held target, then run deterministic evaluators first."""

    def __init__(self, llm: ChatGrader, router: MathRouterService | None = None):
        self.llm = llm
        self.router = router or MathRouterService()

    def evaluate(
        self,
        student_answer: str,
        question_ref: str,
        outline: Sequence[HomeworkExercise],
    ) -> EvaluationResult:
        target = next((item for item in outline if item.ref == question_ref), None)
        if target is None:
            return EvaluationResult(
                verdict=None,
                authoritative=False,
                question_ref=question_ref,
                target_type="exercise",
                tool_used="unresolved",
                reason="unresolved_question",
            )

        raw_candidates = _numeric_candidates(student_answer)
        raw_candidate = (
            raw_candidates[0]
            if len(raw_candidates) == 1
            else _terminal_result_candidate(student_answer)
        )
        # Digits win where there are any; words are read only where the
        # deterministic evaluators would otherwise abstain and hand an answer
        # that is plainly right to a fallback that cannot record it.
        candidate = raw_candidate or _spoken_number_candidate(student_answer) or student_answer

        deterministic = None
        if target.expected_answer:
            deterministic = self.router.validate_student_answer(
                target.text, target.expected_answer, candidate
            )
        if deterministic is None or deterministic.is_equivalent is None:
            deterministic = self.router.verify_chat_answer(target.text, candidate)
        if deterministic.is_equivalent is None:
            deterministic = self._evaluate_equation(target.text, candidate)

        if deterministic.is_equivalent is not None:
            steps = tuple(deterministic.steps_data)
            if not steps:
                steps = (
                    f"expected: {deterministic.canonical_answer}",
                    f"student: {candidate}",
                )
            return EvaluationResult(
                verdict=deterministic.is_equivalent,
                authoritative=True,
                question_ref=question_ref,
                target_type=target.target_type,
                skill=target.skill,
                tool_used=deterministic.tool_used,
                correct_answer=deterministic.canonical_answer,
                steps=steps,
                steps_visible_to_student=False,
            )

        try:
            grade = self.llm.grade_chat_answer(target.text, student_answer)
        except LLMError:
            grade = None
        return EvaluationResult(
            verdict=grade.is_correct if grade else None,
            authoritative=False,
            question_ref=question_ref,
            target_type=target.target_type,
            skill=target.skill,
            tool_used="llm_fallback",
            correct_answer=grade.correct_answer if grade else None,
            reason="deterministic_evaluator_abstained",
        )

    @staticmethod
    def _evaluate_equation(question: str, candidate: str):
        from app.math.router import _extract_equation
        from app.math.schemas import ToolResult

        equation = _extract_equation(question)
        student = parse_to_fraction(candidate)
        solutions = SymPyMathService().solve_equation(equation) if equation else None
        if not solutions or len(solutions) != 1 or student is None:
            return ToolResult(False, "sympy_equation", is_equivalent=None)
        expected = solutions[0]
        expected_fraction = expected if hasattr(expected, "denominator") else None
        if expected_fraction is None:
            return ToolResult(False, "sympy_equation", is_equivalent=None)
        canonical = canonical_fraction_str(expected_fraction)
        return ToolResult(
            True,
            "sympy_equation",
            canonical_answer=canonical,
            is_equivalent=student == expected_fraction,
            steps_data=[f"solve: {equation}", f"= {canonical}"],
        )
