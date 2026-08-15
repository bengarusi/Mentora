"""The tutor remembers what it drew, and a board follows the conversation.

Two behaviours a student notices immediately when they are missing: asking "why
did you cross that out?" and being told the tutor cannot see the board, and
pressing "explain on board" only to be re-taught the topic from the beginning.
"""

import pytest

from app.board.digest import digest_for
from app.core.config import settings
from app.lesson.context import LessonContext
from app.llm import prompts
from app.llm.provider import TutorContext
from app.models.board_explanation import BoardExplanation
from app.models.message import Message
from app.models.session import LessonSession
from app.schemas.board import BoardSpec
from app.services.board_service import BoardService
from tests.conftest import make_student
from tests.fake_llm import FakeLLMProvider


@pytest.fixture(autouse=True)
def board_enabled(monkeypatch):
    monkeypatch.setattr(settings, "BOARD_EXPLANATION_ENABLED", True)


def _spec(**overrides) -> BoardSpec:
    data = {
        "title": "Multiplying by 10",
        "intro": "Let's look at this together.",
        "blocks": [
            {
                "kind": "steps",
                "id": "s1",
                "caption": "Two groups of five",
                "narration": "You can count five, five more.",
                "items": [
                    {"math": "2 \\times 5", "operation": "means 2 groups of 5"},
                    {"math": "5 + 5 = 10", "emphasis": "circle", "emphasis_tone": "good"},
                ],
            },
            {
                "kind": "callout",
                "id": "c1",
                "caption": "A reminder",
                "narration": "Two fives make ten.",
                "tone": "insight",
                "text": "2 times 5 gives 10 because 5 plus 5 is 10.",
            },
        ],
    }
    data.update(overrides)
    return BoardSpec.model_validate(data)


def _session(db, student) -> LessonSession:
    session = LessonSession(
        student_id=student.id,
        subject="math",
        topic="Multiplication",
        subtopic="Multiplying by 10",
        goal_text="I want to multiply numbers by 10.",
        phase="teaching",
        difficulty="medium",
    )
    db.add(session)
    db.flush()
    return session


# ---- the digest ------------------------------------------------------------

def test_the_digest_numbers_the_blocks_so_step_two_means_something():
    """'I didn't understand step 2' has to resolve to a specific thing."""
    text = digest_for(_spec(), char_budget=700)

    assert "1. steps:" in text
    assert "2. insight note:" in text


def test_the_digest_records_the_marks_the_tutor_made():
    """Without this, 'why did you circle that?' is unanswerable."""
    text = digest_for(_spec(), char_budget=700)

    assert "circle mark" in text


def test_the_digest_carries_no_rendering_detail():
    """Coordinates and ranges say nothing a conversation needs, and paying for
    them in every later prompt is waste."""
    spec = _spec(
        blocks=[
            {
                "kind": "steps",
                "id": "s1",
                "caption": "steps",
                "narration": "n",
                "items": [{"math": "y = 2x"}],
            },
            {
                "kind": "coordinate_plane",
                "id": "p1",
                "caption": "graph",
                "narration": "n",
                "x_min": -1,
                "x_max": 5,
                "y_min": -1,
                "y_max": 11,
                "lines": [{"slope": 2, "intercept": 1}],
            },
        ]
    )

    text = digest_for(spec, char_budget=700)

    assert "y = 2.0x + 1.0" in text
    assert "x_min" not in text and "slope_triangle" not in text


def test_an_oversized_digest_is_truncated_rather_than_dropped():
    """A partial memory of the board still beats none — the student is asking
    about it either way."""
    text = digest_for(_spec(), char_budget=60)

    assert len(text) <= 60
    assert text.endswith("…")


# ---- recall into the chat --------------------------------------------------

def test_a_board_shown_in_this_lesson_reaches_the_next_chat_prompt(db_session):
    student = make_student(db_session)
    session = _session(db_session, student)
    BoardService(db_session, FakeLLMProvider(), student).open_lesson_on_board(session.id)

    ctx = LessonContext(db_session, session, student, FakeLLMProvider()).build_tutor_context()
    _, user = prompts.chat_prompt(ctx, "why did you do that bit?")

    assert ctx.board_digests, "the board must be recalled into the tutor's context"
    assert "BOARDS YOU ALREADY DREW" in user
    assert "On the board" in user


def test_only_the_digest_reaches_the_prompt_not_the_whole_spec(db_session):
    """The full spec stays rendering data. Shipping it into every later prompt
    would be expensive and mostly noise."""
    student = make_student(db_session)
    session = _session(db_session, student)
    db_session.add(
        BoardExplanation(
            session_id=session.id,
            kind="lesson_intro",
            message_id=None,
            title="Multiplying by 10",
            content_json=_spec().model_dump(mode="json"),
        )
    )
    db_session.flush()

    ctx = LessonContext(db_session, session, student, FakeLLMProvider()).build_tutor_context()
    _, user = prompts.chat_prompt(ctx, "what did you circle?")

    assert "circle mark" in user
    assert '"emphasis_tone"' not in user and '"kind": "steps"' not in user


def test_only_the_most_recent_boards_are_recalled(db_session, monkeypatch):
    monkeypatch.setattr(settings, "BOARD_DIGEST_LIMIT", 2)
    student = make_student(db_session)
    session = _session(db_session, student)
    for index in range(4):
        db_session.add(
            BoardExplanation(
                session_id=session.id,
                kind="chat",
                title=f"Board {index}",
                content_json=_spec(title=f"Board {index}").model_dump(mode="json"),
            )
        )
    db_session.flush()

    ctx = LessonContext(db_session, session, student, FakeLLMProvider()).build_tutor_context()

    assert len(ctx.board_digests) == 2
    assert "Board 3" in ctx.board_digests[-1]


def test_a_board_that_can_no_longer_be_parsed_does_not_break_the_chat(db_session):
    """A stale board is the tutor forgetting one, never a dead conversation."""
    student = make_student(db_session)
    session = _session(db_session, student)
    db_session.add(
        BoardExplanation(
            session_id=session.id,
            kind="chat",
            title="From an older schema",
            content_json={"title": "old", "blocks": [{"kind": "gone"}]},
        )
    )
    db_session.flush()

    ctx = LessonContext(db_session, session, student, FakeLLMProvider()).build_tutor_context()

    assert ctx.board_digests == []


def test_boards_are_not_recalled_when_the_feature_is_off(db_session, monkeypatch):
    student = make_student(db_session)
    session = _session(db_session, student)
    BoardService(db_session, FakeLLMProvider(), student).open_lesson_on_board(session.id)
    monkeypatch.setattr(settings, "BOARD_EXPLANATION_ENABLED", False)

    ctx = LessonContext(db_session, session, student, FakeLLMProvider()).build_tutor_context()

    assert ctx.board_digests == []


# ---- a chat board follows the conversation ---------------------------------

def _lesson_ctx() -> TutorContext:
    return TutorContext(
        subject="math",
        topic="Multiplication",
        subtopic="Multiplying by 10",
        goal_text="I want to multiply numbers by 10.",
        grade="5",
        age=10,
        difficulty="medium",
        recent_messages=[("tutor", "Now you try one. What is 3 times 4?")],
    )


def test_a_focused_board_leads_with_the_conversation_not_the_lesson_topic():
    """Regression: leading with the subtopic made the board re-teach 'multiplying
    by 10' when the student asked about 3 x 4."""
    _, user = prompts.board_lesson_prompt(
        _lesson_ctx(), max_blocks=6, focus="Tutor: What is 3 times 4?"
    )

    assert user.index("3 times 4") < user.index("Multiplying by 10")
    assert "NOT the subject of this board" in user
    assert "do not repeat the board" in user.lower()


def test_the_lesson_opening_board_still_leads_with_the_lesson():
    _, user = prompts.board_lesson_prompt(_lesson_ctx(), max_blocks=6)

    assert user.startswith("Subject: math")
    assert "PRESSED 'EXPLAIN ON BOARD'" not in user
