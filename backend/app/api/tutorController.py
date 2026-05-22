from fastapi import APIRouter, Depends

from app.api.dependencies import get_tutor_service
from app.schemas.assessment import (
    AnswerSubmit,
    GradedAnswerDTO,
    QuestionDTO,
    SessionSummary,
)
from app.schemas.tutor import PhaseResult, TurnRequest, TurnResult
from app.services.tutor_service import TutorService

router = APIRouter(prefix="/tutor", tags=["tutor"])


@router.post("/{session_id}/turn", response_model=TurnResult)
def send_student_message_and_get_tutor_reply(
    session_id: int,
    body: TurnRequest,
    tutor: TutorService = Depends(get_tutor_service),
):
    return tutor.send_student_message_and_get_tutor_reply(session_id, body.content)


@router.post("/{session_id}/advance", response_model=PhaseResult)
def advance_lesson_to_next_phase(
    session_id: int,
    tutor: TutorService = Depends(get_tutor_service),
):
    return tutor.move_lesson_to_next_phase(session_id)


@router.post("/{session_id}/assessment/start", response_model=list[QuestionDTO])
def start_assessment_questions(
    session_id: int,
    tutor: TutorService = Depends(get_tutor_service),
):
    return tutor.begin_assessment_and_generate_questions(session_id)


@router.post("/{session_id}/assessment/answer", response_model=GradedAnswerDTO)
def submit_assessment_answer(
    session_id: int,
    body: AnswerSubmit,
    tutor: TutorService = Depends(get_tutor_service),
):
    return tutor.submit_and_grade_assessment_answer(
        session_id, body.question_id, body.answer
    )


@router.get("/{session_id}/summary", response_model=SessionSummary)
def get_lesson_summary(
    session_id: int,
    tutor: TutorService = Depends(get_tutor_service),
):
    return tutor.get_or_generate_session_summary(session_id)
