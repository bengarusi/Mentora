from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from app.core.enums import LessonPhase, SuccessLevel
from app.models.assessment import AssessmentQuestion
from app.models.performance import Performance
from app.schemas.tutor import GradedAnswer

if TYPE_CHECKING:
    from app.lesson.context import LessonContext

TOTAL_QUESTIONS = 3


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


class ExplanationState(_ConversationalState):
    phase = LessonPhase.EXPLANATION

    def generate_phase_opening_message(self, ctx: "LessonContext") -> str:
        text = ctx.llm.generate_explanation(ctx.build_tutor_context())
        ctx.save_tutor_message_to_db(text)
        return text

    def get_next_phase_state(self, ctx: "LessonContext") -> "LessonState":
        return ExampleState()


class ExampleState(_ConversationalState):
    phase = LessonPhase.EXAMPLE

    def generate_phase_opening_message(self, ctx: "LessonContext") -> str:
        text = ctx.llm.generate_example(ctx.build_tutor_context())
        ctx.save_tutor_message_to_db(text)
        return text

    def get_next_phase_state(self, ctx: "LessonContext") -> "LessonState":
        return AssessmentState()


class AssessmentState(LessonState):
    phase = LessonPhase.ASSESSMENT

    def generate_phase_opening_message(self, ctx: "LessonContext") -> str:
        text = "Great! Now let's check what you've learned with 3 questions."
        ctx.save_tutor_message_to_db(text)
        return text

    def generate_reply_to_student_message(
        self, ctx: "LessonContext", text: str
    ) -> str:
        raise InvalidLessonAction(
            "During the assessment, please answer the questions."
        )

    def get_next_phase_state(self, ctx: "LessonContext") -> "LessonState":
        raise InvalidLessonAction("Finish answering the 3 questions first.")

    # ---- assessment-specific actions ----

    def generate_assessment_questions(
        self, ctx: "LessonContext"
    ) -> list[AssessmentQuestion]:
        existing = ctx.questions.get_specific_session_questions(ctx.session.id)
        if existing:
            return existing
        generated = ctx.llm.generate_questions(ctx.build_tutor_context())
        rows: list[AssessmentQuestion] = []
        for g in generated:
            rows.append(
                ctx.questions.add(
                    AssessmentQuestion(
                        session_id=ctx.session.id,
                        difficulty=g.difficulty,
                        question_text=g.question,
                        criteria=g.criteria,
                    )
                )
            )
        return rows

    def grade_and_save_student_answer(
        self, ctx: "LessonContext", question_id: int, answer: str
    ) -> tuple[GradedAnswer, int]:
        questions = ctx.questions.get_specific_session_questions(ctx.session.id)
        question = next((q for q in questions if q.id == question_id), None)
        if question is None:
            raise InvalidLessonAction("Question not found for this session.")
        if question.is_correct is not None:
            raise InvalidLessonAction("This question was already answered.")

        graded = ctx.llm.grade_answer(
            question.question_text, question.criteria or "", answer
        )
        question.student_answer = answer
        question.is_correct = graded.is_correct
        question.feedback = graded.feedback
        ctx.db.flush()

        remaining = TOTAL_QUESTIONS - ctx.questions.count_checked_answers(ctx.session.id)
        if remaining <= 0:
            self.finalize_assessment_and_record_performance(ctx)
        return graded, max(remaining, 0)

    def finalize_assessment_and_record_performance(
        self, ctx: "LessonContext"
    ) -> None:
        questions = ctx.questions.get_specific_session_questions(ctx.session.id)
        score = sum(1 for q in questions if q.is_correct)
        level = self.determine_success_level_from_score(score)
        ctx.performances.add(
            Performance(
                session_id=ctx.session.id,
                success_level=level.value,
                score=score,
            )
        )
        ctx.move_to_next_phase_of_the_conversation(LessonPhase.CORRECTION)
        ctx.state.generate_phase_opening_message(ctx)

    @staticmethod
    def determine_success_level_from_score(score: int) -> SuccessLevel:
        if score >= TOTAL_QUESTIONS:
            return SuccessLevel.ACHIEVED
        if score >= 1:
            return SuccessLevel.PARTIALLY
        return SuccessLevel.NOT_ACHIEVED


class CorrectionState(_ConversationalState):
    phase = LessonPhase.CORRECTION

    def generate_phase_opening_message(self, ctx: "LessonContext") -> str:
        questions = ctx.questions.get_specific_session_questions(ctx.session.id)
        wrong = [q for q in questions if q.is_correct is False]
        if not wrong:
            text = "Excellent work — you answered all the questions correctly!"
        else:
            missed = "; ".join(f"'{q.question_text}'" for q in wrong)
            prompt = (
                "The student answered these questions incorrectly: "
                f"{missed}. Gently explain the correct approach for each one."
            )
            text = ctx.llm.chat_reply(ctx.build_tutor_context(), prompt)
        ctx.save_tutor_message_to_db(text)
        return text

    def get_next_phase_state(self, ctx: "LessonContext") -> "LessonState":
        return LevelAdjustmentState()


class LevelAdjustmentState(_ConversationalState):
    phase = LessonPhase.LEVEL_ADJUSTMENT

    def generate_phase_opening_message(self, ctx: "LessonContext") -> str:
        perf = ctx.performances.get_specific_session_performance(ctx.session.id)
        score = perf.score if perf else 0
        adjustment = ctx.llm.adjust_level(ctx.build_tutor_context(), score)
        ctx.save_tutor_message_to_db(adjustment.note)
        return adjustment.note

    def get_next_phase_state(self, ctx: "LessonContext") -> "LessonState":
        return CompletedState()


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


_STATE_BY_PHASE: dict[LessonPhase, type[LessonState]] = {
    LessonPhase.EXPLANATION: ExplanationState,
    LessonPhase.EXAMPLE: ExampleState,
    LessonPhase.ASSESSMENT: AssessmentState,
    LessonPhase.CORRECTION: CorrectionState,
    LessonPhase.LEVEL_ADJUSTMENT: LevelAdjustmentState,
    LessonPhase.COMPLETED: CompletedState,
}


def state_for_phase(phase: LessonPhase) -> LessonState:
    return _STATE_BY_PHASE[phase]()
