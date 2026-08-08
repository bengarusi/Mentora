import logging

from sqlalchemy.orm import Session

from app.core.enums import LessonPhase, MessageRole, Subject
from app.llm.provider import LLMProvider, TutorContext
from app.models.message import Message
from app.models.session import LessonSession
from app.models.student import Student
from app.repositories.assessment_repo import AssessmentRepository
from app.repositories.message_repo import MessageRepository
from app.repositories.performance_repo import PerformanceRepository

log = logging.getLogger("app.lesson.context")

_HISTORY_LIMIT = 10


class LessonContext:
    """Context object of the State pattern. Built fresh per request; the only
    cross-request state is the session.phase column (single source of truth).
    The current LessonState is rehydrated from that column."""

    def __init__(
        self,
        db: Session,
        session: LessonSession,
        student: Student,
        llm: LLMProvider,
    ):
        self.db = db
        self.session = session
        self.student = student
        self.llm = llm
        self.messages = MessageRepository(db)
        self.questions = AssessmentRepository(db)
        self.performances = PerformanceRepository(db)

        from app.lesson.state import state_for_phase

        self.state = state_for_phase(LessonPhase(session.phase))

    def move_to_next_phase_of_the_conversation(self, phase: LessonPhase) -> None:
        from app.lesson.state import state_for_phase

        previous_phase = self.session.phase
        self.session.phase = phase.value
        self.state = state_for_phase(phase)
        log.info(
            "phase transition session_id=%s from=%s to=%s",
            self.session.id,
            previous_phase,
            phase.value,
        )

    def save_tutor_message_to_db(self, content: str) -> Message:
        return self.messages.add(
            Message(
                session_id=self.session.id,
                role=MessageRole.TUTOR.value,
                content=content,
            )
        )

    def save_student_message_to_db(self, content: str) -> Message:
        return self.messages.add(
            Message(
                session_id=self.session.id,
                role=MessageRole.STUDENT.value,
                content=content,
            )
        )

    def build_tutor_context(self) -> TutorContext:
        if self.session.subject == Subject.MATH.value:
            level = self.student.math_level
        else:
            level = self.student.english_level

        history = self.messages.get_recent_session_messages(
            self.session.id, _HISTORY_LIMIT
        )
        recent = [(m.role, m.content) for m in history]

        return TutorContext(
            subject=self.session.subject,
            topic=self.session.topic,
            goal_text=self.session.goal_text,
            grade=self.student.grade,
            age=self.student.age,
            level=level,
            recent_messages=recent,
            subtopic=getattr(self.session, "subtopic", None),
            difficulty=getattr(self.session, "difficulty", None),
        )
