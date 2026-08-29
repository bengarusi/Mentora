"""Answers said out loud, as transcription writes them.

Speech comes back as words — "three quarters", not "3/4" — and the deterministic
evaluators only read digits. Without this the student who speaks the right
answer is told "correct" by a fallback that records nothing, and stays on the
same exercise with the counter unmoved.
"""

import pytest

from app.agent.evaluation import AnswerEvaluator, _spoken_number_candidate
from app.agent.schemas import HomeworkExercise


@pytest.mark.parametrize(
    ("said", "expected"),
    [
        ("three quarters", "3/4"),
        ("Three quarters.", "3/4"),
        ("three-quarters", "3/4"),
        ("one half", "1/2"),
        ("a half", "1/2"),
        ("two thirds", "2/3"),
        ("seven", "7"),
        ("twenty five", "25"),
        ("negative three", "-3"),
        ("zero", "0"),
        ("the answer is three quarters", "3/4"),
        ("I think it is seven", "7"),
    ],
)
def test_a_number_said_in_words_is_read(said, expected):
    assert _spoken_number_candidate(said) == expected


@pytest.mark.parametrize(
    "said",
    [
        "one more time",
        "can you explain that again",
        "I have no idea",
        "",
        "half of what",
        "yes",
    ],
)
def test_words_that_are_not_an_answer_are_left_alone(said):
    assert _spoken_number_candidate(said) is None


class _GraderMustNotBeAsked:
    def grade_chat_answer(self, question_text, student_answer):
        raise AssertionError("a spoken answer must be settled deterministically")


def _outline():
    return [
        HomeworkExercise(
            ref="exercise-1",
            text="What is 1/2 + 1/4?",
            target_type="exercise",
            expected_answer="3/4",
            skill="fractions",
        )
    ]


def test_a_spoken_correct_answer_is_authoritative():
    result = AnswerEvaluator(_GraderMustNotBeAsked()).evaluate(
        "Three quarters.", "exercise-1", _outline()
    )

    assert result.authoritative is True
    assert result.verdict is True


def test_a_spoken_wrong_answer_is_authoritative_too():
    result = AnswerEvaluator(_GraderMustNotBeAsked()).evaluate(
        "one half", "exercise-1", _outline()
    )

    assert result.authoritative is True
    assert result.verdict is False


def test_digits_still_win_over_words():
    result = AnswerEvaluator(_GraderMustNotBeAsked()).evaluate(
        "3/4", "exercise-1", _outline()
    )

    assert result.authoritative is True
    assert result.verdict is True


# ---------------------------------------------------------------------------
# Arithmetic as a worksheet writes it
# ---------------------------------------------------------------------------

def test_a_worksheets_multiplication_sign_is_understood():
    """Worksheets write 7 x 8; only "*" was ever parsed, so it went unchecked."""
    for text in ("What is 7 x 8?", "What is 7 × 8?", "Exercise 2: What is 7 x 8?"):
        result = AnswerEvaluator(_GraderMustNotBeAsked()).evaluate(
            "56", "exercise-1", [HomeworkExercise(ref="exercise-1", text=text)]
        )
        assert result.authoritative is True, text
        assert result.verdict is True, text


def test_a_wrong_answer_to_a_multiplication_is_still_authoritative():
    result = AnswerEvaluator(_GraderMustNotBeAsked()).evaluate(
        "54", "exercise-1", [HomeworkExercise(ref="exercise-1", text="What is 7 x 8?")]
    )

    assert result.authoritative is True
    assert result.verdict is False


def test_a_division_sign_is_understood():
    result = AnswerEvaluator(_GraderMustNotBeAsked()).evaluate(
        "3", "exercise-1", [HomeworkExercise(ref="exercise-1", text="What is 12 ÷ 4?")]
    )

    assert result.authoritative is True
    assert result.verdict is True


def test_algebra_keeps_its_x():
    """The x in 2x + 3 is a variable, not a multiplication sign."""
    from app.files.homework import normalize_arithmetic

    assert normalize_arithmetic("Solve 2x + 3 = 11") == "Solve 2x + 3 = 11"
    assert normalize_arithmetic("What is 7 x 8?") == "What is 7 * 8?"
