from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_student, get_tutor_service
from app.db.database import get_db
from app.models.student import Student
from app.repositories.message_repo import MessageRepository
from app.repositories.session_repo import SessionRepository
from app.schemas.message import MessageResponse
from app.schemas.session import SessionCreate, SessionResponse
from app.services.session_service import end_session, get_owned_session_or_404
from app.services.tutor_service import TutorService

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("/", response_model=SessionResponse)
def create_new_session(
    data: SessionCreate,
    tutor: TutorService = Depends(get_tutor_service),
):
    return tutor.create_lesson_and_generate_first_explanation(data)


@router.get("/", response_model=list[SessionResponse])
def list_my_sessions(
    db: Session = Depends(get_db),
    student: Student = Depends(get_current_student),
):
    return SessionRepository(db).get_lesson_list_for_student(student.id)


@router.get("/{session_id}", response_model=SessionResponse)
def get_session(
    session_id: int,
    db: Session = Depends(get_db),
    student: Student = Depends(get_current_student),
):
    return get_owned_session_or_404(db, student.id, session_id)


@router.post("/{session_id}/end", response_model=SessionResponse)
def end_existing_session(
    session_id: int,
    db: Session = Depends(get_db),
    student: Student = Depends(get_current_student),
):
    return end_session(db, student.id, session_id)


@router.get("/{session_id}/messages", response_model=list[MessageResponse])
def get_session_messages(
    session_id: int,
    db: Session = Depends(get_db),
    student: Student = Depends(get_current_student),
):
    get_owned_session_or_404(db, student.id, session_id)
    return MessageRepository(db).get_specific_session_messages_history(session_id)
