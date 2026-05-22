from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.enums import LessonPhase, SessionStatus
from app.lesson.context import LessonContext
from app.lesson.state import AssessmentState, InvalidLessonAction
from app.llm.provider import LLMError, LLMProvider
from app.models.session import LessonSession
from app.models.student import Student
from app.repositories.session_repo import SessionRepository
from app.schemas.assessment import (
    GradedAnswerDTO,
    QuestionDTO,
    QuestionResultDTO,
    SessionSummary,
)
from app.schemas.session import SessionCreate
from app.schemas.tutor import PhaseResult, TurnResult


class TutorService:
    """Orchestrates the lesson flow: loads + authorizes the session, drives the
    State machine, persists via repositories, and owns the transaction."""

    def __init__(self, db: Session, llm: LLMProvider, student: Student):
        self.db = db
        self.llm = llm
        self.student = student
        self.sessions = SessionRepository(db)

    # ---- helpers ----

    def build_lesson_context_for_session(
        self, session: LessonSession
    ) -> LessonContext:
        return LessonContext(self.db, session, self.student, self.llm)

    def get_owned_session_or_raise_404(self, session_id: int) -> LessonSession:
        session = self.sessions.get_specific_session(session_id, self.student.id)
        if session is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Session not found"
            )
        return session

    @staticmethod
    def wrap_llm_error_as_http_error(exc: LLMError) -> HTTPException:
        return HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Tutor service unavailable: {exc}",
        )

    # ---- flow ----

    def create_lesson_and_generate_first_explanation(
        self, data: SessionCreate
    ) -> LessonSession:
        session = self.sessions.add(
            LessonSession(
                student_id=self.student.id,
                subject=data.subject.value,
                topic=data.topic,
                goal_text=data.goal_text,
                status=SessionStatus.ACTIVE.value,
                phase=LessonPhase.EXPLANATION.value,
            )
        )
        ctx = self.build_lesson_context_for_session(session)
        try:
            ctx.state.generate_phase_opening_message(ctx)
        except LLMError as exc:
            raise self.wrap_llm_error_as_http_error(exc)
        self.db.commit()
        self.db.refresh(session)
        return session

    def send_student_message_and_get_tutor_reply(
        self, session_id: int, text: str
    ) -> TurnResult:
        session = self.get_owned_session_or_raise_404(session_id)
        ctx = self.build_lesson_context_for_session(session)
        try:
            reply = ctx.state.generate_reply_to_student_message(ctx, text)
        except InvalidLessonAction as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
        except LLMError as exc:
            raise self.wrap_llm_error_as_http_error(exc)
        self.db.commit()
        return TurnResult(tutor_message=reply, phase=session.phase)

    def move_lesson_to_next_phase(self, session_id: int) -> PhaseResult:
        session = self.get_owned_session_or_raise_404(session_id)
        ctx = self.build_lesson_context_for_session(session)
        try:
            next_state = ctx.state.get_next_phase_state(ctx)
            ctx.move_to_next_phase_of_the_conversation(next_state.phase)
            content = ctx.state.generate_phase_opening_message(ctx)
        except InvalidLessonAction as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
        except LLMError as exc:
            raise self.wrap_llm_error_as_http_error(exc)
        self.db.commit()
        return PhaseResult(phase=session.phase, tutor_message=content)

    def begin_assessment_and_generate_questions(
        self, session_id: int
    ) -> list[QuestionDTO]:
        session = self.get_owned_session_or_raise_404(session_id)
        ctx = self.build_lesson_context_for_session(session)

        if session.phase == LessonPhase.EXAMPLE.value:
            ctx.move_to_next_phase_of_the_conversation(LessonPhase.ASSESSMENT)
            ctx.state.generate_phase_opening_message(ctx)

        if not isinstance(ctx.state, AssessmentState):
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "The assessment is not available in this phase.",
            )

        try:
            questions = ctx.state.generate_assessment_questions(ctx)
        except LLMError as exc:
            raise self.wrap_llm_error_as_http_error(exc)
        self.db.commit()
        return [QuestionDTO.model_validate(q) for q in questions]

    def submit_and_grade_assessment_answer(
        self, session_id: int, question_id: int, answer: str
    ) -> GradedAnswerDTO:
        session = self.get_owned_session_or_raise_404(session_id)
        ctx = self.build_lesson_context_for_session(session)
        if not isinstance(ctx.state, AssessmentState):
            raise HTTPException(
                status.HTTP_409_CONFLICT, "No assessment is in progress."
            )
        try:
            graded, remaining = ctx.state.grade_and_save_student_answer(
                ctx, question_id, answer
            )
        except InvalidLessonAction as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
        except LLMError as exc:
            raise self.wrap_llm_error_as_http_error(exc)
        self.db.commit()
        return GradedAnswerDTO(
            question_id=question_id,
            is_correct=graded.is_correct,
            feedback=graded.feedback,
            remaining=remaining,
        )

    def get_or_generate_session_summary(self, session_id: int) -> SessionSummary:
        session = self.get_owned_session_or_raise_404(session_id)
        ctx = self.build_lesson_context_for_session(session)
        perf = ctx.performances.get_specific_session_performance(session_id)

        if perf and not perf.summary_text:
            try:
                perf.summary_text = self.llm.summarize_session(
                    ctx.build_tutor_context()
                )
                self.db.commit()
            except LLMError:
                self.db.rollback()  # summary is best-effort

        questions = ctx.questions.get_specific_session_questions(session_id)
        return SessionSummary(
            session_id=session_id,
            success_level=perf.success_level if perf else None,
            score=perf.score if perf else None,
            summary_text=perf.summary_text if perf else None,
            questions=[QuestionResultDTO.model_validate(q) for q in questions],
        )
