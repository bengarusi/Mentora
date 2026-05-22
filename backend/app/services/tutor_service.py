import logging

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from collections.abc import Iterator

from app.core.enums import LessonPhase, SessionStatus
from app.lesson.context import LessonContext
from app.lesson.state import (
    InvalidLessonAction,
    PracticeState,
    _ConversationalState,
    _annotate_math,
)
from app.llm.provider import LLMError, LLMProvider
from app.models.session import LessonSession
from app.models.student import Student
from app.repositories.session_repo import SessionRepository
from app.schemas.practice import (
    GradedPracticeItem,
    PracticeAnswersSubmit,
    PracticeStartResult,
    PracticeSubmitResult,
    PracticeSummaryDTO,
    PracticeSetResult,
    PracticeQuestionDTO,
)
from app.schemas.session import SessionCreate
from app.schemas.tutor import PhaseResult, TurnResult

log = logging.getLogger("app.services.tutor_service")


class TutorService:
    """Orchestrates the lesson flow: loads + authorizes the session, drives the
    State machine, persists via repositories, and owns the transaction."""

    def __init__(self, db: Session, llm: LLMProvider, student: Student):
        self.db = db
        self.llm = llm
        self.student = student
        self.sessions = SessionRepository(db)

    # ---- helpers ----

    def _build_ctx(self, session: LessonSession) -> LessonContext:
        return LessonContext(self.db, session, self.student, self.llm)

    def _get_session(self, session_id: int) -> LessonSession:
        session = self.sessions.get_specific_session(session_id, self.student.id)
        if session is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Session not found"
            )
        return session

    def _require_phase(self, session: LessonSession, phase: LessonPhase) -> None:
        if session.phase != phase.value:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"This action requires phase '{phase.value}', current phase is '{session.phase}'.",
            )

    def _require_practice_phase(self, session: LessonSession) -> None:
        self._require_phase(session, LessonPhase.PRACTICE)

    @staticmethod
    def _llm_error(exc: LLMError) -> HTTPException:
        return HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Tutor service unavailable: {exc}",
        )

    # ---- session creation ----

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
                phase=LessonPhase.TEACHING.value,
            )
        )
        ctx = self._build_ctx(session)
        try:
            ctx.state.generate_phase_opening_message(ctx)
        except LLMError as exc:
            raise self._llm_error(exc)
        self.db.commit()
        self.db.refresh(session)
        log.info(
            "lesson created session_id=%s student_id=%s subject=%s topic=%s phase=%s",
            session.id,
            self.student.id,
            session.subject,
            session.topic,
            session.phase,
        )
        return session

    # ---- chat turn (TEACHING and SUMMARY phases) ----

    def send_student_message_and_get_tutor_reply(
        self, session_id: int, text: str
    ) -> TurnResult:
        session = self._get_session(session_id)
        ctx = self._build_ctx(session)
        try:
            reply = ctx.state.generate_reply_to_student_message(ctx, text)
        except InvalidLessonAction as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
        except LLMError as exc:
            raise self._llm_error(exc)
        self.db.commit()
        return TurnResult(tutor_message=reply, phase=session.phase)

    # ---- streaming chat turn (token-by-token) ----

    def stream_student_message_and_get_tutor_reply(
        self, session_id: int, text: str
    ) -> Iterator[str]:
        """Stream the tutor's reply as text deltas.

        Phase is validated up front (so a wrong phase becomes a clean 409 before
        the stream starts). The student message is staged, the reply streamed,
        and both messages committed atomically once the stream completes — so a
        dropped stream leaves no orphaned student message."""
        session = self._get_session(session_id)
        ctx = self._build_ctx(session)
        if not isinstance(ctx.state, _ConversationalState):
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "You can only chat during the teaching or summary phase.",
            )

        ctx.save_student_message_to_db(text)
        self.db.flush()  # visible to the history query below, not yet committed
        tutor_ctx = ctx.build_tutor_context()
        annotated = _annotate_math(text)

        def generate() -> Iterator[str]:
            chunks: list[str] = []
            for delta in self.llm.chat_reply_stream(tutor_ctx, annotated):
                chunks.append(delta)
                yield delta
            full = "".join(chunks).strip()
            if full:
                ctx.save_tutor_message_to_db(full)
            self.db.commit()

        return generate()

    # ---- phase advance (TEACHING→PRE_PRACTICE_EXAMPLE, PRACTICE_SUMMARY→SUMMARY, SUMMARY→COMPLETED) ----

    def move_lesson_to_next_phase(self, session_id: int) -> PhaseResult:
        session = self._get_session(session_id)
        ctx = self._build_ctx(session)
        try:
            next_state = ctx.state.get_next_phase_state(ctx)
            ctx.move_to_next_phase_of_the_conversation(next_state.phase)
            content = ctx.state.generate_phase_opening_message(ctx)
        except InvalidLessonAction as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
        except LLMError as exc:
            raise self._llm_error(exc)
        self.db.commit()
        return PhaseResult(phase=session.phase, tutor_message=content)

    # ---- practice: start (PRE_PRACTICE_EXAMPLE → PRACTICE + set 1) ----

    def start_practice(self, session_id: int) -> PracticeStartResult:
        session = self._get_session(session_id)
        if session.phase not in (
            LessonPhase.PRE_PRACTICE_EXAMPLE.value,
            LessonPhase.PRACTICE.value,  # idempotent if already started
        ):
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Practice can only be started from the pre-practice example phase.",
            )
        ctx = self._build_ctx(session)

        # Transition to PRACTICE if not there yet
        if session.phase == LessonPhase.PRE_PRACTICE_EXAMPLE.value:
            ctx.move_to_next_phase_of_the_conversation(LessonPhase.PRACTICE)
            ctx.state.generate_phase_opening_message(ctx)

        if not isinstance(ctx.state, PracticeState):
            raise HTTPException(status.HTTP_409_CONFLICT, "Practice is not active.")

        try:
            questions = ctx.state.generate_practice_set(ctx, set_number=1)
        except LLMError as exc:
            raise self._llm_error(exc)

        self.db.commit()
        return PracticeStartResult(
            set_number=1,
            questions=[PracticeQuestionDTO.model_validate(q) for q in questions],
        )

    # ---- practice: submit answers for the current set ----

    def submit_practice_set(
        self, session_id: int, body: PracticeAnswersSubmit
    ) -> PracticeSubmitResult:
        session = self._get_session(session_id)
        self._require_practice_phase(session)
        ctx = self._build_ctx(session)

        if not isinstance(ctx.state, PracticeState):
            raise HTTPException(status.HTTP_409_CONFLICT, "No practice in progress.")

        answers = {item.question_id: item.answer for item in body.answers}
        if not answers:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "No answers submitted.")

        # Determine which set these answers belong to (by question IDs)
        first_qid = next(iter(answers))
        first_q = ctx.questions.get(first_qid)
        if first_q is None or first_q.session_id != session.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Question not found in this session.")
        set_number = first_q.set_number

        try:
            results = ctx.state.grade_and_save_set_answers(ctx, set_number, answers)
        except LLMError as exc:
            raise self._llm_error(exc)

        self.db.commit()

        grades = [
            GradedPracticeItem(
                question_id=q.id,
                question_text=q.question_text,
                difficulty=q.difficulty,
                set_number=q.set_number,
                student_answer=q.student_answer or "",
                is_correct=bool(q.is_correct),
                feedback=q.feedback or "",
                correct_answer=q.correct_answer,
                solution_steps=q.solution_steps,
                explanation=q.explanation,
            )
            for q, _ in results
        ]
        return PracticeSubmitResult(set_number=set_number, grades=grades)

    # ---- practice: generate next set ----

    def next_practice_set(self, session_id: int) -> PracticeStartResult:
        session = self._get_session(session_id)
        self._require_practice_phase(session)
        ctx = self._build_ctx(session)

        if not isinstance(ctx.state, PracticeState):
            raise HTTPException(status.HTTP_409_CONFLICT, "No practice in progress.")

        current_max = ctx.questions.get_latest_set_number(session_id)
        next_set = current_max + 1

        try:
            questions = ctx.state.generate_practice_set(ctx, set_number=next_set)
        except LLMError as exc:
            raise self._llm_error(exc)

        self.db.commit()
        return PracticeStartResult(
            set_number=next_set,
            questions=[PracticeQuestionDTO.model_validate(q) for q in questions],
        )

    # ---- practice: finish → PRACTICE_SUMMARY ----

    def finish_practice(self, session_id: int) -> PhaseResult:
        session = self._get_session(session_id)
        self._require_practice_phase(session)
        ctx = self._build_ctx(session)

        if not isinstance(ctx.state, PracticeState):
            raise HTTPException(status.HTTP_409_CONFLICT, "No practice in progress.")

        # Save aggregated performance before moving to summary
        ctx.state.finalize_practice_and_record_performance(ctx)

        ctx.move_to_next_phase_of_the_conversation(LessonPhase.PRACTICE_SUMMARY)
        self.db.commit()
        return PhaseResult(phase=LessonPhase.PRACTICE_SUMMARY.value)

    # ---- practice summary data ----

    def get_practice_summary(self, session_id: int) -> PracticeSummaryDTO:
        session = self._get_session(session_id)
        ctx = self._build_ctx(session)
        perf = ctx.performances.get_specific_session_performance(session_id)

        all_questions = ctx.questions.get_specific_session_questions(session_id)

        # Group by set_number
        sets_map: dict[int, list] = {}
        for q in all_questions:
            sn = q.set_number or 1
            sets_map.setdefault(sn, []).append(q)

        sets = [
            PracticeSetResult(
                set_number=sn,
                questions=[
                    GradedPracticeItem(
                        question_id=q.id,
                        question_text=q.question_text,
                        difficulty=q.difficulty,
                        set_number=q.set_number,
                        student_answer=q.student_answer or "",
                        is_correct=bool(q.is_correct) if q.is_correct is not None else False,
                        feedback=q.feedback or "",
                        correct_answer=q.correct_answer,
                        solution_steps=q.solution_steps,
                        explanation=q.explanation,
                    )
                    for q in sorted(qs, key=lambda x: x.difficulty)
                ],
            )
            for sn, qs in sorted(sets_map.items())
        ]

        total_correct = perf.score if perf else sum(1 for q in all_questions if q.is_correct)
        total_questions = perf.total_questions if perf else len(all_questions)

        return PracticeSummaryDTO(
            session_id=session_id,
            total_correct=total_correct,
            total_questions=total_questions,
            success_level=perf.success_level if perf else None,
            sets=sets,
        )

    # ---- final lesson summary (for summary page after the lesson) ----

    def get_or_generate_final_summary_text(self, session_id: int) -> str | None:
        """
        Return the lesson summary text for the summary page.

        Priority:
          1. Performance.summary_text already set (saved by SummaryState).
          2. Lazy-generate from LLM if the session is in SUMMARY or COMPLETED phase
             and no text was stored yet (e.g. legacy sessions).
        """
        session = self._get_session(session_id)
        ctx = self._build_ctx(session)
        perf = ctx.performances.get_specific_session_performance(session_id)

        if perf is None:
            return None

        if perf.summary_text:
            return perf.summary_text

        # Legacy / fallback: generate on demand if phase allows
        if session.phase in (LessonPhase.SUMMARY.value, LessonPhase.COMPLETED.value):
            try:
                text = self.llm.generate_lesson_summary(
                    ctx.build_tutor_context(),
                    perf.score,
                    perf.total_questions,
                )
                perf.summary_text = text
                self.db.commit()
                return text
            except LLMError:
                self.db.rollback()

        return None
