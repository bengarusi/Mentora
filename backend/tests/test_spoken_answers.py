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
