from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from app.core.enums import LessonPhase, SuccessLevel
from app.math.router import MathRouterService
from app.math.schemas import ToolResult
from app.models.assessment import AssessmentQuestion
from app.models.performance import Performance
from app.schemas.tutor import GradedAnswer

if TYPE_CHECKING:
    from app.lesson.context import LessonContext

log = logging.getLogger(__name__)
_math_router = MathRouterService()

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
        # Pass an annotated version to the LLM so equivalent fractions like
        # "2/4" are shown as "2/4 [= 1/2]" — the LLM evaluates correctness
        # against the simplified form rather than guessing.
        reply = ctx.llm.chat_reply(ctx.build_tutor_context(), _annotate_math(text))
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
        # Return UI text without persisting — this is navigation copy, not an LLM message.
        # Persisting it causes it to re-appear as a stale message when the student
        # returns to the chat in the SUMMARY phase.
        return "Great — let's practice! Here are your first 3 questions."

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
            validated_answer = _validate_generated_answer(
                g.question, g.correct_answer
            )
            rows.append(
                ctx.questions.add(
                    AssessmentQuestion(
                        session_id=ctx.session.id,
                        set_number=set_number,
                        difficulty=g.difficulty,
                        question_text=g.question,
                        correct_answer=validated_answer,
                        solution_steps=g.solution_steps,
                        explanation=g.explanation,
                        criteria=validated_answer,  # grading fallback
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

            # 1. Deterministic validation (source of truth for is_correct)
            tool_result = _math_router.validate_student_answer(
                q.question_text, criteria, raw_answer
            )

            if tool_result.is_equivalent is not None:
                # Tool gave a definitive answer — use it; ask LLM only for feedback
                is_correct = tool_result.is_equivalent
                llm_grade = ctx.llm.grade_answer(q.question_text, criteria, raw_answer)
                graded = GradedAnswer(
                    is_correct=is_correct,
                    feedback=llm_grade.feedback,
                )
                if tool_result.warnings:
                    log.warning(
                        "Math tool warnings for question %d: %s",
                        q.id,
                        tool_result.warnings,
                    )
            else:
                # Tool could not determine — fall back to LLM for both fields
                log.info(
                    "Math tool could not validate question %d (%s); using LLM fallback.",
                    q.id,
                    tool_result.tool_used,
                )
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
        # Also persist to Performance so SummaryPage can retrieve it reliably
        # without depending on message ordering.
        if perf is not None:
            perf.summary_text = text
            ctx.db.flush()
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
# Math-tool helpers used by PracticeState and _ConversationalState
# ---------------------------------------------------------------------------

def _annotate_math(text: str) -> str:
    """If the student's message is a parseable number/fraction, append its
    simplified canonical form so the LLM cannot misjudge equivalence.
    Example: "2/4" → "2/4 [= 1/2]"
    The original text is saved to the DB unchanged; only the LLM sees this."""
    from app.math.normalizer import canonical_fraction_str, parse_to_fraction

    stripped = text.strip()
    frac = parse_to_fraction(stripped)
    if frac is not None:
        canonical = canonical_fraction_str(frac)
        if canonical != stripped:
            return f"{stripped} [= {canonical}]"
    return text


def _validate_generated_answer(question_text: str, llm_answer: str) -> str:
    """
    Try to independently compute the answer to *question_text* and compare
    with the LLM-provided *llm_answer*.

    If the tool can compute an answer AND it differs from the LLM answer,
    override with the deterministically computed answer (and log a warning).

    If the tool cannot compute an answer, trust the LLM answer as-is.
    Returns the best available answer string.
    """
    result: ToolResult = _math_router.try_compute_correct_answer(
        question_text, llm_answer
    )

    if result.success and result.canonical_answer and result.is_equivalent is False:
        # LLM answer is wrong — override with the computed canonical answer
        log.warning(
            "LLM generated incorrect correct_answer='%s' for question '%s'. "
            "Overriding with computed answer='%s'.",
            llm_answer,
            question_text[:80],
            result.canonical_answer,
        )
        return result.canonical_answer

    if result.success and result.canonical_answer and result.is_equivalent is True:
        # LLM answer is correct but may not be in canonical form — normalise it
        return result.canonical_answer

    # Tool could not verify — keep LLM answer unchanged
    return llm_answer


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
