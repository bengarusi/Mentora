from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from app.core.enums import LessonPhase, SuccessLevel
from app.models.assessment import AssessmentQuestion
from app.models.performance import Performance
from app.schemas.tutor import GradedAnswer

if TYPE_CHECKING:
    from app.lesson.context import LessonContext

QUESTIONS_PER_SET = 3


class InvalidLessonAction(Exception):
    """Raised when an action isn't allowed in the current lesson phase."""


class LessonState(ABC):
    """Base State. Each concrete state owns its phase-specific behavior and the
    legal transition to the next phase."""

    phase: LessonPhase

    @abstractmethod
    def generate_phase_opening_message(self, ctx: "LessonContext") -> str | None:
        """Produce and persist the tutor's opening message for this phase."""

    @abstractmethod
    def generate_reply_to_student_message(
        self, ctx: "LessonContext", text: str
    ) -> str:
        """Handle one conversational turn and return the tutor's reply."""

    @abstractmethod
    def get_next_phase_state(self, ctx: "LessonContext") -> "LessonState":
        """Return the state for the next phase (without persisting the change)."""


class _ConversationalState(LessonState):
    """Shared chat behavior for phases where the student may talk to the tutor."""

    def generate_reply_to_student_message(
        self, ctx: "LessonContext", text: str
    ) -> str:
        ctx.save_student_message_to_db(text)
        reply = ctx.llm.chat_reply(ctx.build_tutor_context(), text)
        ctx.save_tutor_message_to_db(reply)
        return reply


# ---------------------------------------------------------------------------
# Teaching phase — merged explanation + examples + interactive mini-questions
# ---------------------------------------------------------------------------

class TeachingState(_ConversationalState):
    phase = LessonPhase.TEACHING

    def generate_phase_opening_message(self, ctx: "LessonContext") -> str:
        text = ctx.llm.generate_teaching_intro(ctx.build_tutor_context())
        ctx.save_tutor_message_to_db(text)
        return text

    def get_next_phase_state(self, ctx: "LessonContext") -> "LessonState":
        return PrePracticeExampleState()


# ---------------------------------------------------------------------------
# Pre-practice guided example — read-only screen before real practice
# ---------------------------------------------------------------------------

class PrePracticeExampleState(LessonState):
    phase = LessonPhase.PRE_PRACTICE_EXAMPLE

    def generate_phase_opening_message(self, ctx: "LessonContext") -> str:
        text = ctx.llm.generate_pre_practice_example(ctx.build_tutor_context())
        ctx.save_tutor_message_to_db(text)
        return text

    def generate_reply_to_student_message(
        self, ctx: "LessonContext", text: str
    ) -> str:
        raise InvalidLessonAction(
            "You are reviewing the guided example. Click 'Start Practice' when ready."
        )

    def get_next_phase_state(self, ctx: "LessonContext") -> "LessonState":
        return PracticeState()


# ---------------------------------------------------------------------------
# Practice phase — multiple sets of 3 questions each
# ---------------------------------------------------------------------------

class PracticeState(LessonState):
    phase = LessonPhase.PRACTICE

    def generate_phase_opening_message(self, ctx: "LessonContext") -> str:
        text = "Great — let's practice! Here are your first 3 questions."
        ctx.save_tutor_message_to_db(text)
        return text

    def generate_reply_to_student_message(
        self, ctx: "LessonContext", text: str
    ) -> str:
        raise InvalidLessonAction(
            "During practice, please submit your answers using the answer fields."
        )

    def get_next_phase_state(self, ctx: "LessonContext") -> "LessonState":
        return PracticeSummaryState()

    # ---- practice-specific actions ----

    def generate_practice_set(
        self, ctx: "LessonContext", set_number: int
    ) -> list[AssessmentQuestion]:
        existing = ctx.questions.get_practice_set_questions(ctx.session.id, set_number)
        if existing:
            return existing
        generated = ctx.llm.generate_practice_questions(
            ctx.build_tutor_context(), set_number
        )
        rows: list[AssessmentQuestion] = []
        for g in generated:
            rows.append(
                ctx.questions.add(
                    AssessmentQuestion(
                        session_id=ctx.session.id,
                        set_number=set_number,
                        difficulty=g.difficulty,
                        question_text=g.question,
                        correct_answer=g.correct_answer,
                        solution_steps=g.solution_steps,
                        explanation=g.explanation,
                        criteria=g.correct_answer,  # grading fallback
                    )
                )
            )
        return rows

    def grade_and_save_set_answers(
        self,
        ctx: "LessonContext",
        set_number: int,
        answers: dict[int, str],  # {question_id: student_answer}
    ) -> list[tuple[AssessmentQuestion, GradedAnswer]]:
        """Grade every submitted answer for one set. Returns (question, grade) pairs."""
        questions = ctx.questions.get_practice_set_questions(ctx.session.id, set_number)
        results: list[tuple[AssessmentQuestion, GradedAnswer]] = []

        for q in questions:
            raw_answer = answers.get(q.id)
            if raw_answer is None:
                continue
            criteria = q.correct_answer or q.criteria or ""
            graded = ctx.llm.grade_answer(q.question_text, criteria, raw_answer)
            q.student_answer = raw_answer
            q.is_correct = graded.is_correct
            q.feedback = graded.feedback
            results.append((q, graded))

        ctx.db.flush()
        return results

    def finalize_practice_and_record_performance(
        self, ctx: "LessonContext"
    ) -> Performance:
        """Tally all sets, compute SuccessLevel, and persist a Performance row."""
        all_questions = ctx.questions.get_specific_session_questions(ctx.session.id)
        answered = [q for q in all_questions if q.is_correct is not None]
        total_questions = len(answered)
        total_correct = sum(1 for q in answered if q.is_correct)
        latest_set = ctx.questions.get_latest_set_number(ctx.session.id)
        level = self._success_level(total_correct, total_questions)

        perf = ctx.performances.get_specific_session_performance(ctx.session.id)
        if perf is None:
            perf = ctx.performances.add(
                Performance(
                    session_id=ctx.session.id,
                    success_level=level.value,
                    score=total_correct,
                    total_questions=total_questions,
                    practice_sets=latest_set,
                )
            )
        else:
            perf.success_level = level.value
            perf.score = total_correct
            perf.total_questions = total_questions
            perf.practice_sets = latest_set
            ctx.db.flush()
        return perf

    @staticmethod
    def _success_level(correct: int, total: int) -> SuccessLevel:
        if total == 0 or correct == 0:
            return SuccessLevel.NOT_ACHIEVED
        pct = correct / total
        if pct >= 0.70:
            return SuccessLevel.ACHIEVED
        return SuccessLevel.PARTIALLY


# ---------------------------------------------------------------------------
# Practice Summary — frontend reads stored data; backend is a marker state
# ---------------------------------------------------------------------------

class PracticeSummaryState(LessonState):
    phase = LessonPhase.PRACTICE_SUMMARY

    def generate_phase_opening_message(self, ctx: "LessonContext") -> str | None:
        return None

    def generate_reply_to_student_message(
        self, ctx: "LessonContext", text: str
    ) -> str:
        raise InvalidLessonAction(
            "Review your practice results, then click 'Continue to Summary'."
        )

    def get_next_phase_state(self, ctx: "LessonContext") -> "LessonState":
        return SummaryState()


# ---------------------------------------------------------------------------
# Summary — final lesson summary message generated in chat
# ---------------------------------------------------------------------------

class SummaryState(_ConversationalState):
    phase = LessonPhase.SUMMARY

    def generate_phase_opening_message(self, ctx: "LessonContext") -> str:
        perf = ctx.performances.get_specific_session_performance(ctx.session.id)
        total_correct = perf.score if perf else 0
        total_questions = perf.total_questions if perf else 0
        text = ctx.llm.generate_lesson_summary(
            ctx.build_tutor_context(), total_correct, total_questions
        )
        ctx.save_tutor_message_to_db(text)
        return text

    def get_next_phase_state(self, ctx: "LessonContext") -> "LessonState":
        return CompletedState()


# ---------------------------------------------------------------------------
# Completed — terminal state
# ---------------------------------------------------------------------------

class CompletedState(LessonState):
    phase = LessonPhase.COMPLETED

    def generate_phase_opening_message(self, ctx: "LessonContext") -> str | None:
        return None

    def generate_reply_to_student_message(
        self, ctx: "LessonContext", text: str
    ) -> str:
        raise InvalidLessonAction("This lesson is already completed.")

    def get_next_phase_state(self, ctx: "LessonContext") -> "LessonState":
        raise InvalidLessonAction("This lesson is already completed.")


# ---------------------------------------------------------------------------
# Phase → state registry
# ---------------------------------------------------------------------------

_STATE_BY_PHASE: dict[LessonPhase, type[LessonState]] = {
    LessonPhase.TEACHING: TeachingState,
    LessonPhase.PRE_PRACTICE_EXAMPLE: PrePracticeExampleState,
    LessonPhase.PRACTICE: PracticeState,
    LessonPhase.PRACTICE_SUMMARY: PracticeSummaryState,
    LessonPhase.SUMMARY: SummaryState,
    LessonPhase.COMPLETED: CompletedState,
}


def state_for_phase(phase: LessonPhase) -> LessonState:
    try:
        return _STATE_BY_PHASE[phase]()
    except KeyError:
        # Old-style session with a deprecated phase value — treat as completed
        return CompletedState()
