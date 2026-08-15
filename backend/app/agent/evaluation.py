from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Protocol

from app.agent.schemas import EvaluationResult, HomeworkExercise
from app.llm.provider import LLMError
from app.math.normalizer import canonical_fraction_str, parse_to_fraction
from app.math.router import MathRouterService
from app.math.sympy_service import SymPyMathService

_NUMERIC_CANDIDATE = re.compile(
    r"(?<![\w/])-?\d+(?:\s+\d+\s*/\s*\d+|\s*/\s*\d+|\.\d+|%)?(?![\w/])"
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
        raw_candidate = raw_candidates[0] if len(raw_candidates) == 1 else None
        candidate = raw_candidate or student_answer

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
