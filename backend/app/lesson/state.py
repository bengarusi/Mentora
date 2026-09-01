from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING

from app.core.enums import DifficultyLevel, LessonPhase, SuccessLevel
from app.llm.provider import LLMError
from app.lesson.reply_policy import ensure_tutor_reply_is_coherent
from app.math.router import MathRouterService
from app.math.schemas import ToolResult
from app.models.assessment import AssessmentQuestion
from app.models.performance import Performance
from app.schemas.tutor import GradedAnswer

if TYPE_CHECKING:
    from app.lesson.context import LessonContext
    from app.llm.provider import LLMProvider

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
        # against the simplified form rather than guessing. The raw message is
        # also the retrieval query, so any relevant uploaded material is pulled in.
        reply = ctx.llm.chat_reply(
            ctx.build_tutor_context(text), _annotate_math(text)
        )
        ctx.save_tutor_message_to_db(reply)
        return reply


# ---------------------------------------------------------------------------
# Teaching phase — merged explanation + examples + interactive mini-questions
# ---------------------------------------------------------------------------

class TeachingState(_ConversationalState):
    phase = LessonPhase.TEACHING

    def generate_phase_opening_message(self, ctx: "LessonContext") -> str:
        # The very first message of a lesson always asks the student to pick a
        # difficulty level (via the chat UI's level buttons) before any teaching
        # content is generated — deterministic, no LLM call needed here.
        from app.llm.prompts import difficulty_selection_message

        text = difficulty_selection_message()
        ctx.save_tutor_message_to_db(text)
        return text

    def generate_reply_to_student_message(
        self, ctx: "LessonContext", text: str
    ) -> str:
        ctx.save_student_message_to_db(text)
        tutor_ctx = ctx.build_tutor_context(text)
        # Grade the student's answer to the question the tutor just asked, then
        # lock that verdict into the reply prompt — the chat LLM invents the
        # question and can't be trusted to grade its own answer (it marked a
        # correct answer wrong repeatedly). The math tool decides arithmetic;
        # an isolated grading call handles everything it can't compute.
        verdict = verify_chat_answer(tutor_ctx.recent_messages, text, ctx.llm)
        reply = ctx.llm.chat_reply(
            tutor_ctx, _annotate_math(text), verification=verdict
        )
        reply = ensure_tutor_reply_is_coherent(
            reply, verdict, tutor_ctx.recent_messages
        )
        ctx.save_tutor_message_to_db(reply)
        return reply

    def get_next_phase_state(self, ctx: "LessonContext") -> "LessonState":
        return PrePracticeExampleState()


# ---------------------------------------------------------------------------
# Homework Help — a single-phase guided conversation over an uploaded file
# ---------------------------------------------------------------------------

class HomeworkHelpState(_ConversationalState):
    """Terminal, conversational phase for the Homework Help flow.

    Inheriting _ConversationalState is what makes both streaming paths, voice,
    and answer-grading work here for free; the pedagogy differs entirely in the
    prompt layer, which branches on the session's mode."""

    phase = LessonPhase.HOMEWORK_HELP

    def generate_phase_opening_message(self, ctx: "LessonContext") -> str:
        text = ctx.llm.generate_homework_intro(ctx.build_tutor_context())
        ctx.save_tutor_message_to_db(text)
        return text

    def generate_reply_to_student_message(
        self, ctx: "LessonContext", text: str
    ) -> str:
        ctx.save_student_message_to_db(text)
        if _homework_agent_should_run(ctx, text):
            from app.agent.runner import AgentRunner

            try:
                with ctx.db.begin_nested():
                    reply = AgentRunner(
                        ctx.db, ctx.llm, ctx.student, ctx.session
                    ).run(text, turn_id=ctx.turn_id)
                ctx.save_tutor_message_to_db(reply)
                return reply
            except Exception:  # noqa: BLE001 - the legacy path is the live fallback
                log.exception(
                    "homework agent failed; using legacy reply session_id=%s",
                    ctx.session.id,
                )
        # Deliberately NO locked verdict here, unlike the teaching chat.
        #
        # verify_chat_answer grades the student against the tutor's most recent
        # question. That is sound in teaching, where the tutor invents the
        # question and the student answers exactly it. In homework help the
        # questions live in the uploaded file and the tutor asks scaffolding
        # sub-steps, so the student may answer the sub-step, the whole exercise,
        # or reason aloud. Grading the wrong pairing produced a confidently
        # wrong verdict the prompt then forced the tutor to obey — telling a
        # student their correct working was wrong. An unlocked reply is better
        # than an authoritative mis-grade.
        #
        # This also matches what the streaming paths already do (they only
        # verify for TeachingState), so typed, voice, and streamed turns agree.
        reply = ctx.llm.chat_reply(
            ctx.build_tutor_context(text), _annotate_math(text)
        )
        ctx.save_tutor_message_to_db(reply)
        return reply

    def get_next_phase_state(self, ctx: "LessonContext") -> "LessonState":
        raise InvalidLessonAction(
            "Homework Help doesn't have phases — just keep chatting."
        )


def _homework_agent_should_run(ctx: "LessonContext", text: str) -> bool:
    """Flag + capability + deterministic Fast Path gate."""
    from app.agent.registry import outline_from_json
    from app.agent.routing import might_need_tools
    from app.agent.stores import SessionStateStore
    from app.core.config import settings
    from app.llm.tool_protocol import ToolCallingLLM

    if not settings.AGENT_ENABLED_HOMEWORK or not isinstance(ctx.llm, ToolCallingLLM):
        return False
    state = SessionStateStore(ctx.db).load(ctx.session.id)
    outline = outline_from_json(ctx.session.homework_outline)
    should_run = might_need_tools(
        text, state, outline_refs=[item.ref for item in outline]
    )
    log.info(
        "homework agent route session_id=%s path=%s",
        ctx.session.id,
        "agent" if should_run else "fast",
    )
    return should_run


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
        # The level the lesson stands at right now — whatever the student last
        # chose in the chat — is what these questions were written for, and is
        # what each correct answer will be credited at.
        level = ctx.session.difficulty or DifficultyLevel.MEDIUM.value
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
                        level=level,
                        question_text=g.question,
                        correct_answer=validated_answer,
                        solution_steps=g.solution_steps,
                        explanation=g.explanation,
                        criteria=validated_answer,  # grading fallback
                    )
                )
            )
        log.info(
            "generated practice set session_id=%s set_number=%d count=%d level=%s",
            ctx.session.id,
            set_number,
            len(rows),
            level,
        )
        return rows

    def grade_and_save_set_answers(
        self,
        ctx: "LessonContext",
        set_number: int,
        answers: dict[int, str],  # {question_id: student_answer}
    ) -> list[tuple[AssessmentQuestion, GradedAnswer]]:
        """Grade every submitted answer for one set. Returns (question, grade) pairs.

        Correctness comes from the deterministic math tool whenever it can decide,
        so correct answers need NO LLM call (instant). The LLM is only used to
        explain *wrong* answers (and as a full fallback when the tool abstains),
        and those calls run concurrently so a whole set costs ~one round-trip.

        A question already answered correctly is closed: answering it again is
        re-submitting work that is done, so it is neither re-graded nor re-scored.
        A wrong answer stays open — retrying it is the point of practice."""
        questions = ctx.questions.get_practice_set_questions(ctx.session.id, set_number)
        settled = {q.id for q in questions if q.is_correct}

        # Phase 1: deterministic pass. Decide is_correct and which questions still
        # need an LLM call for prose feedback.
        decided: dict[int, GradedAnswer] = {}  # question_id -> grade (no LLM needed)
        needs_llm: list[tuple[AssessmentQuestion, str, str, ToolResult | None]] = []

        for q in questions:
            raw_answer = answers.get(q.id)
            if raw_answer is None or q.id in settled:
                continue
            criteria = q.correct_answer or q.criteria or ""
            tool_result = _math_router.validate_student_answer(
                q.question_text, criteria, raw_answer
            )

            if tool_result.warnings:
                log.warning(
                    "Math tool warnings for question %d: %s", q.id, tool_result.warnings
                )

            if tool_result.is_equivalent is True:
                # Correct — skip the LLM entirely, use instant templated praise.
                decided[q.id] = GradedAnswer(
                    is_correct=True, feedback=_correct_feedback()
                )
            elif tool_result.is_equivalent is False:
                # Wrong but definitive — LLM explains why (is_correct stays False).
                needs_llm.append((q, criteria, raw_answer, tool_result))
            else:
                # Tool abstained — LLM owns both fields (full fallback).
                log.info(
                    "Math tool could not validate question %d (%s); using LLM fallback.",
                    q.id,
                    tool_result.tool_used,
                )
                needs_llm.append((q, criteria, raw_answer, None))

        # Phase 2: run the remaining LLM feedback calls concurrently.
        llm_grades: dict[int, GradedAnswer] = {}
        if needs_llm:

            def _grade(item):
                q, criteria, raw_answer, tool_result = item
                grade = ctx.llm.grade_answer(
                    q.question_text, criteria, raw_answer, tool_result=tool_result
                )
                if tool_result is not None:
                    # Tool is the source of truth for is_correct on definitive verdicts.
                    grade = GradedAnswer(
                        is_correct=tool_result.is_equivalent, feedback=grade.feedback
                    )
                return q.id, grade

            with ThreadPoolExecutor(max_workers=len(needs_llm)) as pool:
                for qid, grade in pool.map(_grade, needs_llm):
                    llm_grades[qid] = grade

        # Phase 3: persist results in the original question order.
        results: list[tuple[AssessmentQuestion, GradedAnswer]] = []
        for q in questions:
            if q.id not in answers:
                continue
            if q.id in settled:
                # Replayed as it was first earned, so the results page is whole
                # without the answer being counted a second time.
                results.append(
                    (q, GradedAnswer(is_correct=True, feedback=q.feedback or _correct_feedback()))
                )
                continue
            graded = decided.get(q.id) or llm_grades[q.id]
            q.student_answer = answers[q.id]
            q.is_correct = graded.is_correct
            q.feedback = graded.feedback
            results.append((q, graded))

        ctx.db.flush()
        correct = sum(1 for _, g in results if g.is_correct)
        log.info(
            "graded set session_id=%s set_number=%d correct=%d total=%d llm_calls=%d",
            ctx.session.id,
            set_number,
            correct,
            len(results),
            len(needs_llm),
        )
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
        log.info(
            "performance recorded session_id=%s score=%d/%d level=%s sets=%d",
            ctx.session.id,
            total_correct,
            total_questions,
            level.value,
            latest_set,
        )
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

def _correct_feedback() -> str:
    """Templated praise for a correct answer — used instead of an LLM call."""
    return "Correct! Nice work."


def verify_chat_answer(
    recent_messages: list[tuple[str, str]],
    student_text: str,
    llm: "LLMProvider",
) -> ToolResult | None:
    """Grade a teaching-chat answer against the question the tutor just asked,
    returning an authoritative verdict (ToolResult with is_equivalent set) the
    reply prompt must obey — or None to let the tutor reply normally.

    Two-stage, "tool first, LLM second":
      1. The deterministic math tool decides arithmetic / fractions / decimals /
         percentages with certainty.
      2. When the tool abstains (place value, comparisons, word problems, prose
         or Hebrew questions it can't compute), an ISOLATED grading call — which
         sees only the question and answer, not the conversation — decides. That
         isolation is what fixes the original bug: the in-conversation model got
         stuck repeating a wrong verdict it had already given.

    recent_messages is (role, content) oldest→newest and already includes the
    student's just-saved message, so the question is the most recent tutor turn.
    """
    from app.core.enums import MessageRole

    last_question = next(
        (
            content
            for role, content in reversed(recent_messages)
            if role == MessageRole.TUTOR.value
        ),
        None,
    )
    if not last_question or not _looks_like_answer(last_question, student_text):
        return None

    # 1. Deterministic — exact and instant where it applies.
    result = _math_router.verify_chat_answer(last_question, student_text)
    if result.is_equivalent is not None:
        return result

    # 2. Isolated LLM grade — general coverage for everything the tool can't compute.
    try:
        grade = llm.grade_chat_answer(last_question, student_text)
    except LLMError:
        return None  # grading is best-effort; never block the reply
    if grade.is_correct is None:
        return None
    return ToolResult(
        success=True,
        tool_used="chat_llm_grade",
        canonical_answer=grade.correct_answer,
        is_equivalent=grade.is_correct,
    )


def _looks_like_answer(question: str, student_text: str) -> bool:
    """Cheap guard so we only grade actual answers — not the student asking
    their own question, and not chit-chat after a tutor turn that asked nothing."""
    from app.math.normalizer import parse_to_fraction

    s = student_text.strip()
    if not s or s.endswith("?"):
        return False
    if "?" in question:
        return True
    return parse_to_fraction(s) is not None


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
    LessonPhase.HOMEWORK_HELP: HomeworkHelpState,
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
