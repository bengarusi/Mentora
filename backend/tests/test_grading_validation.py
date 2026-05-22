"""
Tests for the deterministic-validation → LLM-feedback grading pipeline.

Covers:
  1. 1/3 + 1/3, student answers 2/3          → correct
  2. 1/3 + 1/3, student first answers 2       → partial (incorrect), then 2/3 → correct
  3. 1/4 + 1/4, student answers 2/4           → correct (equivalent to 1/2)
  4. 1/2 + 1/2, student answers 2/2           → correct (equivalent to 1)
  5. 1/3 + 1/3, student answers 1/3           → incorrect
  6. When validation is correct, FakeLLM feedback must not include corrective phrases
     and grade_prompt must hard-lock is_correct=true in the JSON template.
"""

import pytest

from app.math.router import MathRouterService
from app.math.schemas import ToolResult
from app.llm.prompts import grade_prompt
from tests.fake_llm import FakeLLMProvider

_CORRECTIVE_PHRASES = (
    "almost right",
    "not quite",
    "good try",
    "let's check",
    "let me check",
    "close",
    "but",
    "however",
    "actually",
)

_router = MathRouterService()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _validate(question: str, expected: str, student: str) -> ToolResult:
    return _router.validate_student_answer(question, expected, student)


def _fake_grade(question: str, expected: str, student: str, tool: ToolResult):
    return FakeLLMProvider().grade_answer(
        question, expected, student, tool_result=tool
    )


# ---------------------------------------------------------------------------
# Test 1 — exact correct answer
# ---------------------------------------------------------------------------

def test_correct_answer_2_3_for_1_3_plus_1_3():
    q = "What is 1/3 + 1/3?"
    expected = "2/3"
    student = "2/3"

    tool = _validate(q, expected, student)
    assert tool.is_equivalent is True, "Validator should confirm 2/3 == 2/3"

    grade = _fake_grade(q, expected, student, tool)
    assert grade.is_correct is True
    assert not any(p in grade.feedback.lower() for p in _CORRECTIVE_PHRASES), (
        f"Correct answer feedback must not include corrective phrases; got: {grade.feedback!r}"
    )


# ---------------------------------------------------------------------------
# Test 2 — partial then correct
# ---------------------------------------------------------------------------

def test_partial_answer_2_is_incorrect_for_1_3_plus_1_3():
    q = "What is 1/3 + 1/3?"
    expected = "2/3"
    student = "2"  # numerator only — a valid step but not the final fraction

    tool = _validate(q, expected, student)
    assert tool.is_equivalent is False, (
        "Validator should mark '2' as not equivalent to '2/3'"
    )

    grade = _fake_grade(q, expected, student, tool)
    assert grade.is_correct is False


def test_correct_answer_after_partial_for_1_3_plus_1_3():
    q = "What is 1/3 + 1/3?"
    expected = "2/3"
    student = "2/3"

    tool = _validate(q, expected, student)
    assert tool.is_equivalent is True

    grade = _fake_grade(q, expected, student, tool)
    assert grade.is_correct is True
    assert not any(p in grade.feedback.lower() for p in _CORRECTIVE_PHRASES)


# ---------------------------------------------------------------------------
# Test 3 — equivalent unsimplified fraction
# ---------------------------------------------------------------------------

def test_equivalent_fraction_2_4_correct_for_1_4_plus_1_4():
    q = "What is 1/4 + 1/4?"
    expected = "1/2"
    student = "2/4"

    tool = _validate(q, expected, student)
    assert tool.is_equivalent is True, (
        "Validator must accept 2/4 as equivalent to 1/2"
    )

    grade = _fake_grade(q, expected, student, tool)
    assert grade.is_correct is True
    assert not any(p in grade.feedback.lower() for p in _CORRECTIVE_PHRASES)


# ---------------------------------------------------------------------------
# Test 4 — whole number equivalent
# ---------------------------------------------------------------------------

def test_fraction_2_2_correct_for_1_2_plus_1_2():
    q = "What is 1/2 + 1/2?"
    # The stored correct_answer might be "1" (canonical) or "2/2" depending on
    # how the question was generated.  Test both directions.
    for expected in ("1", "2/2"):
        tool = _validate(q, expected, "2/2")
        assert tool.is_equivalent is True, (
            f"Validator must accept '2/2' as equivalent to '{expected}'"
        )
        grade = _fake_grade(q, expected, "2/2", tool)
        assert grade.is_correct is True
        assert not any(p in grade.feedback.lower() for p in _CORRECTIVE_PHRASES)


# ---------------------------------------------------------------------------
# Test 5 — genuinely wrong answer
# ---------------------------------------------------------------------------

def test_incorrect_answer_1_3_for_1_3_plus_1_3():
    q = "What is 1/3 + 1/3?"
    expected = "2/3"
    student = "1/3"

    tool = _validate(q, expected, student)
    assert tool.is_equivalent is False, (
        "Validator must mark 1/3 as wrong when the expected answer is 2/3"
    )

    grade = _fake_grade(q, expected, student, tool)
    assert grade.is_correct is False


# ---------------------------------------------------------------------------
# Test 6 — prompt structure: correct verdict locks is_correct=true in template
# ---------------------------------------------------------------------------

def test_grade_prompt_locks_is_correct_true_when_tool_says_correct():
    tool = ToolResult(
        success=True,
        tool_used="fraction_arithmetic",
        canonical_answer="2/3",
        is_equivalent=True,
    )
    system, user = grade_prompt(
        "What is 1/3 + 1/3?", "2/3", "2/3", tool_result=tool
    )

    # The system prompt must reference the VALIDATION_RESULT and forbid re-grading
    assert "VALIDATION_RESULT" in system
    assert "is_correct: true" in system
    assert "Do NOT re-grade" in system

    # The user prompt JSON template must hard-code is_correct: true
    assert '"is_correct": true' in user
    assert "is_correct MUST be true" in user

    # The system prompt must instruct the LLM to NOT use corrective phrases.
    # (We check the instruction is present, not that the phrases are absent —
    # listing them as forbidden is intentional and correct.)
    assert "MUST NOT" in system or "must not" in system.lower()


def test_grade_prompt_locks_is_correct_false_when_tool_says_incorrect():
    tool = ToolResult(
        success=True,
        tool_used="fraction_arithmetic",
        canonical_answer="2/3",
        is_equivalent=False,
    )
    system, user = grade_prompt(
        "What is 1/3 + 1/3?", "2/3", "1/3", tool_result=tool
    )

    assert "VALIDATION_RESULT" in system
    assert "is_correct: false" in system
    assert '"is_correct": false' in user
    assert "is_correct MUST be false" in user


def test_fake_llm_feedback_for_correct_answer_has_no_corrective_phrases():
    """Verify FakeLLMProvider (and by extension the grading pipeline) never
    emits corrective language when the validator says the answer is correct."""
    tool = ToolResult(
        success=True,
        tool_used="fraction_arithmetic",
        canonical_answer="2/3",
        is_equivalent=True,
    )
    grade = FakeLLMProvider().grade_answer(
        "What is 1/3 + 1/3?", "2/3", "2/3", tool_result=tool
    )
    assert grade.is_correct is True
    feedback_lower = grade.feedback.lower()
    for phrase in _CORRECTIVE_PHRASES:
        assert phrase not in feedback_lower, (
            f"Feedback for correct answer must not contain '{phrase}'; got: {grade.feedback!r}"
        )


def test_grade_prompt_fallback_when_no_tool_result():
    system, user = grade_prompt("What is 1/3 + 1/3?", "2/3", "2/3")

    # Falls back to the original grading prompt — no VALIDATION_RESULT block
    assert "VALIDATION_RESULT" not in system
    assert "Solve the question yourself" in system
