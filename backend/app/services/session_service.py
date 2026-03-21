from sqlalchemy.orm import Session
from app.models.session import LessonSession
from app.schemas.session import SessionCreate

def create_session(db: Session, data: SessionCreate):
    session = LessonSession(
        student_id=data.student_id,
        subject=data.subject,
        topic=data.topic,
        goal_text=data.goal_text,
        status="active"
    )

    db.add(session)
    db.commit()
    db.refresh(session)

    return session
def end_session(db: Session, session_id: int):
    session = db.query(LessonSession).filter(LessonSession.id == session_id).first()

    if not session:
        return None

    session.status = "ended"
    session.ended_at = func.now()

    db.commit()
    db.refresh(session)

    return session