import logging

from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.sql import func

from app.core.enums import SessionStatus
from app.models.session import LessonSession
from app.repositories.session_repo import SessionRepository

log = logging.getLogger("app.services.session_service")


def get_owned_session_or_404(
    db: Session, student_id: int, session_id: int
) -> LessonSession:
    session = SessionRepository(db).get_specific_session(session_id, student_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Session not found"
        )
    return session


def end_session(db: Session, student_id: int, session_id: int) -> LessonSession:
    session = get_owned_session_or_404(db, student_id, session_id)
    session.status = SessionStatus.ENDED.value
    session.ended_at = func.now()
    db.commit()
    db.refresh(session)
    log.info(
        "session ended session_id=%s student_id=%s", session_id, student_id
    )
    return session
