from sqlalchemy.orm import Session

from app.core.enums import MessageRole, SessionMode
from app.models.message import Message
from app.models.session import LessonSession
from app.repositories.base import BaseRepository


class SessionRepository(BaseRepository[LessonSession]):
    def __init__(self, db: Session):
        super().__init__(db, LessonSession)

    def get_lesson_list_for_student(
        self, student_id: int, mode: SessionMode | None = SessionMode.LESSON
    ) -> list[LessonSession]:
        """Sessions for a student, newest first.

        Defaults to lessons only: Homework Help sessions have no phase ladder
        and no practice score, so counting them as lessons would inflate
        progress stats and offer "Open" links into a lesson UI they can't
        drive. Pass mode=None to get every session regardless."""
        query = self.db.query(LessonSession).filter(
            LessonSession.student_id == student_id
        )
        if mode is not None:
            query = query.filter(LessonSession.mode == mode.value)
        return query.order_by(LessonSession.created_at.desc()).all()

    def get_homework_sessions_with_activity(
        self, student_id: int
    ) -> list[LessonSession]:
        """Homework Help sessions where the student actually said something,
        newest first.

        A session is created the moment "Start Homework Help" is clicked, but
        the conversation only really begins once a file is read and the
        student replies — clicking the button and never following through
        (or navigating away mid-upload) leaves a session with zero real
        activity. Those must not show up as something to "pick up where you
        left off"; this is the only place that distinction is drawn, so the
        empty ones are filtered here rather than hidden ad hoc in the UI."""
        return (
            self.db.query(LessonSession)
            .filter(
                LessonSession.student_id == student_id,
                LessonSession.mode == SessionMode.HOMEWORK.value,
                LessonSession.id.in_(
                    self.db.query(Message.session_id).filter(
                        Message.role == MessageRole.STUDENT.value
                    )
                ),
            )
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
