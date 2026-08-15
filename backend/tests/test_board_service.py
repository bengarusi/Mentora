"""Board generation: anchoring, deduplication, and failure isolation.

The invariants under test are product invariants, not implementation details:
a board belongs to exactly one anchor, is never regenerated once it exists, a
failure to draw one leaves the lesson untouched, and no board exists for a
question the student is still working on.
"""

import pytest
from fastapi import HTTPException

from app.core.config import settings
from app.llm.provider import LLMError
from app.models.assessment import AssessmentQuestion
from app.models.board_explanation import BoardExplanation
from app.models.message import Message
from app.models.session import LessonSession
from app.services.board_service import BoardService
from tests.conftest import make_student
from tests.fake_llm import FakeLLMProvider


@pytest.fixture(autouse=True)
def board_enabled(monkeypatch):
    monkeypatch.setattr(settings, "BOARD_EXPLANATION_ENABLED", True)


def _session(db, student, phase="teaching") -> LessonSession:
    session = LessonSession(
        student_id=student.id,
        subject="math",
        topic="Numbers & Place Value",
        subtopic="Comparing numbers",
        goal_text="I want to compare numbers using <, >, and =.",
        phase=phase,
        difficulty="easy",
    )
    db.add(session)
    db.flush()
    return session


def _question(db, session, **overrides) -> AssessmentQuestion:
    fields = {
        "session_id": session.id,
        "set_number": 1,
        "difficulty": 1,
        "question_text": "Compare 15 and 12 using <, >, or =.",
        "correct_answer": "15 > 12",
        "solution_steps": "1. Compare the tens. 2. 15 is bigger.",
    }
    fields.update(overrides)
    question = AssessmentQuestion(**fields)
    db.add(question)
    db.flush()
    return question


class BoardMustNotCallLLM(FakeLLMProvider):
    """Proves a path is served from storage rather than from the model."""

    def generate_board_explanation(self, system: str, user: str) -> dict:
        raise AssertionError("an existing board must be returned without a model call")


class FailingLLM(FakeLLMProvider):
    def generate_board_explanation(self, system: str, user: str) -> dict:
        raise LLMError("upstream is down")


class InvalidBoardLLM(FakeLLMProvider):
    """Always returns a board with no steps block, so validation always rejects."""

    def __init__(self):
        super().__init__()
        self.attempts = 0

    def generate_board_explanation(self, system: str, user: str) -> dict:
        self.attempts += 1
        self.board_prompts.append((system, user))
        return {
            "title": "Broken",
            "intro": "This board has no steps.",
            "blocks": [
                {
                    "kind": "callout",
                    "id": "c1",
                    "caption": "Tip",
                    "narration": "A tip.",
                    "tone": "insight",
                    "text": "Hi.",
                }
            ],
        }


def _service(db, student, llm=None) -> BoardService:
    return BoardService(db, llm or FakeLLMProvider(), student)


# ---- the lesson board ------------------------------------------------------

def test_opening_a_lesson_on_the_board_anchors_it_to_a_tutor_message(db_session):
    """Anchoring to a message is what puts the board in the transcript, so the
    student can replay it later from where it happened."""
    student = make_student(db_session)
    session = _session(db_session, student)

    board, created = _service(db_session, student).open_lesson_on_board(session.id)

    assert created
    assert board.kind == "lesson_intro"
    assert board.message_id is not None
    message = db_session.get(Message, board.message_id)
    assert message.role == "tutor"
    assert message.content == board.spec.intro


def test_the_lesson_opening_is_generated_once_and_then_replayed(db_session):
    student = make_student(db_session)
    session = _session(db_session, student)
    first, created = _service(db_session, student).open_lesson_on_board(session.id)

    again, created_again = _service(
        db_session, student, BoardMustNotCallLLM()
    ).open_lesson_on_board(session.id)

    assert created and not created_again
    assert again.id == first.id


def test_a_mid_lesson_request_makes_a_new_board_each_time(db_session):
    """Unlike the opening, asking again is asking about something else."""
    student = make_student(db_session)
    session = _session(db_session, student)
    service = _service(db_session, student)

    first, _ = service.open_lesson_on_board(session.id, "why is 8 bigger than 3")
    second, created = service.open_lesson_on_board(session.id, "what does the equals sign mean")

    assert created
    assert first.id != second.id
    assert {first.kind, second.kind} == {"chat"}


def test_the_lesson_prompt_carries_the_goal_and_the_conversation(db_session):
    student = make_student(db_session)
    session = _session(db_session, student)
    db_session.add(Message(session_id=session.id, role="student", content="I am stuck on this"))
    db_session.flush()
    llm = FakeLLMProvider()

    _service(db_session, student, llm).open_lesson_on_board(session.id, "the pointy sign")

    _, user = llm.board_prompts[0]
    assert "Comparing numbers" in user
    assert "compare numbers using" in user
    assert "the pointy sign" in user
    assert "I am stuck on this" in user


def test_the_lesson_board_asks_for_spoken_narration(db_session):
    """The narration is what the tutor says while the block is written, so it has
    to be speakable — no LaTeX, no symbols."""
    student = make_student(db_session)
    session = _session(db_session, student)
    llm = FakeLLMProvider()

    _service(db_session, student, llm).open_lesson_on_board(session.id)

    system, _ = llm.board_prompts[0]
    assert "narration" in system
    assert "read aloud" in system


# ---- the practice review board ---------------------------------------------

def test_a_question_still_being_answered_has_no_board(db_session):
    """During practice the student works it out alone. This is the whole reason
    the board moved out of the answering flow."""
    student = make_student(db_session)
    session = _session(db_session, student, phase="practice")
    question = _question(db_session, session)  # is_correct is None

    with pytest.raises(HTTPException) as exc:
        _service(db_session, student).review_question_on_board(session.id, question.id)

    assert exc.value.status_code == 409
    assert db_session.query(BoardExplanation).count() == 0


def test_a_graded_question_can_be_reviewed_on_the_board(db_session):
    student = make_student(db_session)
    session = _session(db_session, student, phase="practice")
    question = _question(db_session, session, is_correct=False, student_answer="<")

    board, created = _service(db_session, student).review_question_on_board(
        session.id, question.id
    )

    assert created
    assert board.kind == "practice_review"
    assert board.question_id == question.id
    assert board.message_id is None


def test_a_review_board_is_generated_once_per_question(db_session):
    student = make_student(db_session)
    session = _session(db_session, student, phase="practice")
    question = _question(db_session, session, is_correct=False, student_answer="<")
    first, _ = _service(db_session, student).review_question_on_board(session.id, question.id)

    again, created_again = _service(
        db_session, student, BoardMustNotCallLLM()
    ).review_question_on_board(session.id, question.id)

    assert not created_again
    assert again.id == first.id


def test_the_review_prompt_shares_the_students_wrong_answer(db_session):
    student = make_student(db_session)
    session = _session(db_session, student, phase="practice")
    question = _question(
        db_session, session, is_correct=False, student_answer="<", feedback="Check the tens."
    )
    llm = FakeLLMProvider()

    _service(db_session, student, llm).review_question_on_board(session.id, question.id)

    _, user = llm.board_prompts[0]
    assert "The student answered: <" in user
    assert "The verified correct answer is: 15 > 12" in user


def test_a_question_from_another_session_is_not_found(db_session):
    """The FK is the scoping mechanism: a valid question id from elsewhere must
    not resolve, or one question could receive another's explanation."""
    student = make_student(db_session)
    mine = _session(db_session, student, phase="practice")
    theirs = _session(db_session, student, phase="practice")
    other = _question(db_session, theirs, is_correct=True, student_answer=">")

    with pytest.raises(HTTPException) as exc:
        _service(db_session, student).review_question_on_board(mine.id, other.id)

    assert exc.value.status_code == 404


# ---- ownership and architecture --------------------------------------------

def test_another_students_session_is_not_found(db_session):
    owner = make_student(db_session)
    intruder = make_student(db_session, email="intruder@example.com")
    session = _session(db_session, owner)

    with pytest.raises(HTTPException) as exc:
        _service(db_session, intruder).open_lesson_on_board(session.id)

    assert exc.value.status_code == 404


def test_board_service_resolves_sessions_without_depending_on_tutor_service():
    """Services here are siblings sharing repositories, not layers. Reaching into
    TutorService._get_session would couple them through a private method."""
    from pathlib import Path

    source = Path(__file__).parents[1].joinpath("app/services/board_service.py").read_text()
    code = "\n".join(line for line in source.splitlines() if not line.lstrip().startswith("#"))

    assert "from app.services.tutor_service import" not in code
    assert "TutorService(" not in code
    assert "SessionRepository(db)" in code


# ---- deduplication ---------------------------------------------------------

def test_a_concurrent_duplicate_yields_exactly_one_board(db_session):
    """Both racers pay for a generation, but the unique anchor means only one
    board can exist and the loser returns the winner's."""
    student = make_student(db_session)
    session = _session(db_session, student, phase="practice")
    question = _question(db_session, session, is_correct=True, student_answer=">")
    service = _service(db_session, student)
    original_add = service.boards.add

    def add_after_a_competitor_won(board):
        service.boards.add = original_add
        db_session.add(
            BoardExplanation(
                session_id=session.id,
                kind="practice_review",
                question_id=question.id,
                title="Winner",
                content_json=board.content_json,
            )
        )
        db_session.commit()
        return original_add(board)

    service.boards.add = add_after_a_competitor_won
    result, created = service.review_question_on_board(session.id, question.id)

    surviving = (
        db_session.query(BoardExplanation)
        .filter(BoardExplanation.question_id == question.id)
        .all()
    )
    assert not created
    assert len(surviving) == 1
    assert result.id == surviving[0].id


# ---- failure isolation -----------------------------------------------------

def test_a_model_failure_persists_no_board_and_no_message(db_session):
    """A failed board must not leave a dangling tutor turn in the transcript."""
    student = make_student(db_session)
    session = _session(db_session, student)

    with pytest.raises(HTTPException) as exc:
        _service(db_session, student, FailingLLM()).open_lesson_on_board(session.id)

    assert exc.value.status_code == 502
    assert db_session.query(BoardExplanation).count() == 0
    assert db_session.query(Message).count() == 0


def test_an_unusable_board_is_retried_exactly_once_then_fails(db_session):
    student = make_student(db_session)
    session = _session(db_session, student)
    llm = InvalidBoardLLM()

    with pytest.raises(HTTPException) as exc:
        _service(db_session, student, llm).open_lesson_on_board(session.id)

    assert exc.value.status_code == 502
    assert llm.attempts == 2
    assert db_session.query(BoardExplanation).count() == 0


def test_the_retry_tells_the_model_why_it_was_rejected(db_session):
    student = make_student(db_session)
    session = _session(db_session, student)
    llm = InvalidBoardLLM()

    with pytest.raises(HTTPException):
        _service(db_session, student, llm).open_lesson_on_board(session.id)

    first_user, second_user = llm.board_prompts[0][1], llm.board_prompts[1][1]
    assert "rejected because" not in first_user
    assert "no_steps_block" in second_user


# ---- narration -------------------------------------------------------------

def test_narration_is_one_spoken_line_per_block_in_order(db_session):
    student = make_student(db_session)
    session = _session(db_session, student)
    board, _ = _service(db_session, student).open_lesson_on_board(session.id)

    lines = _service(db_session, student).get_narration(session.id, board.id)

    assert lines == [block.narration for block in board.spec.blocks]


def test_a_block_whose_audio_fails_is_skipped_rather_than_killing_the_board(db_session):
    """A silent step beats a board that stops halfway through."""
    import json

    student = make_student(db_session)
    session = _session(db_session, student)
    board, _ = _service(db_session, student).open_lesson_on_board(session.id)

    class HalfBrokenVoice:
        def __init__(self):
            self.calls = 0

        def synthesize_speech(self, text: str) -> str:
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("tts is down for this one")
            return "AAAA"

    events = [
        json.loads(line)
        for line in _service(db_session, student).stream_narration(
            session.id, board.id, HalfBrokenVoice()
        )
    ]

    started = [e["chunk_id"] for e in events if e["type"] == "audio_start"]
    assert started == [1], "block 0 failed, block 1 still speaks"
    assert events[-1]["type"] == "done"


# ---- flag ------------------------------------------------------------------

def test_generating_is_unavailable_when_the_flag_is_off(db_session, monkeypatch):
    monkeypatch.setattr(settings, "BOARD_EXPLANATION_ENABLED", False)
    student = make_student(db_session)
    session = _session(db_session, student)

    with pytest.raises(HTTPException) as exc:
        _service(db_session, student).open_lesson_on_board(session.id)

    assert exc.value.status_code == 404


def test_listing_reports_the_flag_instead_of_failing(db_session, monkeypatch):
    """The list endpoint is capability discovery, so it must answer even when the
    feature is off — otherwise the frontend cannot tell 'disabled' from 'broken'."""
    monkeypatch.setattr(settings, "BOARD_EXPLANATION_ENABLED", False)
    student = make_student(db_session)
    session = _session(db_session, student)

    result = _service(db_session, student).list_boards(session.id)

    assert result.enabled is False
    assert result.boards == []


def test_listing_still_enforces_ownership_when_the_flag_is_off(db_session, monkeypatch):
    monkeypatch.setattr(settings, "BOARD_EXPLANATION_ENABLED", False)
    owner = make_student(db_session)
    intruder = make_student(db_session, email="intruder@example.com")
    session = _session(db_session, owner)

    with pytest.raises(HTTPException) as exc:
        _service(db_session, intruder).list_boards(session.id)

    assert exc.value.status_code == 404
