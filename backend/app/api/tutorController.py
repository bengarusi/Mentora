from fastapi import APIRouter, Depends

from app.api.dependencies import get_tutor_service
from app.schemas.practice import (
    PracticeAnswersSubmit,
    PracticeStartResult,
    PracticeSubmitResult,
    PracticeSummaryDTO,
)
from app.schemas.tutor import PhaseResult, TurnRequest, TurnResult
from app.services.tutor_service import TutorService

router = APIRouter(prefix="/tutor", tags=["tutor"])


# ---------------------------------------------------------------------------
# Teaching phase chat
# ---------------------------------------------------------------------------

@router.post("/{session_id}/turn", response_model=TurnResult)
def send_student_message_and_get_tutor_reply(
    session_id: int,
    body: TurnRequest,
    tutor: TutorService = Depends(get_tutor_service),
):
    return tutor.send_student_message_and_get_tutor_reply(session_id, body.content)


# ---------------------------------------------------------------------------
# Phase advance: TEACHING→PRE_PRACTICE_EXAMPLE, PRACTICE_SUMMARY→SUMMARY, SUMMARY→COMPLETED
# ---------------------------------------------------------------------------

@router.post("/{session_id}/advance", response_model=PhaseResult)
def advance_lesson_to_next_phase(
    session_id: int,
    tutor: TutorService = Depends(get_tutor_service),
):
    return tutor.move_lesson_to_next_phase(session_id)


# ---------------------------------------------------------------------------
# Practice flow
# ---------------------------------------------------------------------------

@router.post("/{session_id}/practice/start", response_model=PracticeStartResult)
def start_practice(
    session_id: int,
    tutor: TutorService = Depends(get_tutor_service),
):
    """Transition PRE_PRACTICE_EXAMPLE → PRACTICE and return the first set of 3 questions."""
    return tutor.start_practice(session_id)


@router.post("/{session_id}/practice/submit", response_model=PracticeSubmitResult)
def submit_practice_set(
    session_id: int,
    body: PracticeAnswersSubmit,
    tutor: TutorService = Depends(get_tutor_service),
):
    """Grade all submitted answers for the current practice set."""
    return tutor.submit_practice_set(session_id, body)


@router.post("/{session_id}/practice/next", response_model=PracticeStartResult)
def next_practice_set(
    session_id: int,
    tutor: TutorService = Depends(get_tutor_service),
):
    """Generate the next practice set with increased difficulty."""
    return tutor.next_practice_set(session_id)


@router.post("/{session_id}/practice/finish", response_model=PhaseResult)
def finish_practice(
    session_id: int,
    tutor: TutorService = Depends(get_tutor_service),
):
    """Finalize practice, record performance, and move to PRACTICE_SUMMARY phase."""
    return tutor.finish_practice(session_id)


@router.get("/{session_id}/practice/summary", response_model=PracticeSummaryDTO)
def get_practice_summary(
    session_id: int,
    tutor: TutorService = Depends(get_tutor_service),
):
    """Return all practice questions with grading results, grouped by set."""
    return tutor.get_practice_summary(session_id)
