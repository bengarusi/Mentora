from sqlalchemy.orm import Session

from app.models.session import LessonSession
from app.repositories.base import BaseRepository


class SessionRepository(BaseRepository[LessonSession]):
    def __init__(self, db: Session):
        super().__init__(db, LessonSession)

    def get_lesson_list_for_student(self, student_id: int) -> list[LessonSession]:
        return (
            self.db.query(LessonSession)
            .filter(LessonSession.student_id == student_id)
            .order_by(LessonSession.created_at.desc())
            .all()
        )

    def get_specific_session(
        self, session_id: int, student_id: int
    ) -> LessonSession | None:
        return (
            self.db.query(LessonSession)
            .filter(
                LessonSession.id == session_id,
                LessonSession.student_id == student_id,
            )
            .first()
        )
