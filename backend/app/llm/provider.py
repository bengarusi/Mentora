from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.math.schemas import ToolResult

from app.schemas.tutor import ChatAnswerGrade, GeneratedPracticeQuestion, GradedAnswer


class LLMError(Exception):
    """Raised when the LLM provider fails (network, parsing, invalid output)."""


@dataclass
class MaterialExcerpt:
    """One passage retrieved from the student's own uploaded study materials.

    Carries its source title so the tutor can say where an explanation came
    from ("in your Fractions worksheet…") instead of quoting anonymously."""

    title: str
    content: str


@dataclass
class TutorContext:
    """Pedagogical context handed to the LLM. Built by TutorService from DB rows,
    so the provider stays database-agnostic and easy to fake in tests."""

    subject: str
    topic: str
    goal_text: str
    grade: str
    age: int
    level: str | None = None  # math_level / english_level for the subject
    recent_messages: list[tuple[str, str]] = field(default_factory=list)  # (role, content)
    subtopic: str | None = None  # precise lesson focus within the topic
    difficulty: str | None = None  # student-chosen easy/medium/hard for this lesson
    #: SessionMode value. Chat prompts branch on this, so the streaming paths
    #: serve homework tutoring without a separate provider method.
    mode: str = "lesson"
    # Only the passages the retriever judged relevant to the current turn —
    # never the student's whole library.
    material_excerpts: list[MaterialExcerpt] = field(default_factory=list)
    # Full text of the homework attached to a Homework Help session.
    homework_text: str | None = None


class LLMProvider(ABC):
    """Strategy interface. Concrete providers (OpenAI, fakes) implement these."""

    @abstractmethod
    def generate_teaching_intro(self, ctx: TutorContext) -> str:
        """Open the teaching phase: explain the topic with examples and invite questions."""

    @abstractmethod
    def chat_reply(
        self,
        ctx: TutorContext,
        student_message: str,
        *,
        verification: "ToolResult | None" = None,
    ) -> str:
        """Respond to one student message during the teaching or summary phase.

        When *verification* carries a definitive is_equivalent verdict, the LLM
        must obey it instead of grading the student's answer itself.
        """

    @abstractmethod
    def chat_reply_stream(
        self,
        ctx: TutorContext,
        student_message: str,
        *,
        verification: "ToolResult | None" = None,
    ) -> Iterator[str]:
        """Stream the reply for one student message as text deltas.

        *verification* has the same authoritative meaning as in chat_reply.
        """

    @abstractmethod
    def generate_homework_intro(self, ctx: TutorContext) -> str:
        """Open a Homework Help session: acknowledge the uploaded work, restate
        the first exercise, and ask the student where they are stuck — without
        solving anything."""

    @abstractmethod
    def summarize_homework_progress(
        self,
        homework_text: str,
        transcript: list[tuple[str, str]],
        total_exercises: int,
    ) -> int:
        """Read the full conversation and return how many exercises the
        student has genuinely solved (0..total_exercises). An exercise the
        student skipped or is mid-attempt on does not count."""

    @abstractmethod
    def generate_difficulty_change_message(
        self, ctx: TutorContext, new_level: str
    ) -> str:
        """Acknowledge a mid-lesson difficulty change and give one fresh example
        at the new level, continuing the teaching conversation."""

    @abstractmethod
    def generate_pre_practice_example(self, ctx: TutorContext) -> str:
        """Produce a fully solved guided example to prepare the student for practice."""

    @abstractmethod
    def generate_practice_questions(
        self, ctx: TutorContext, set_number: int
    ) -> list[GeneratedPracticeQuestion]:
        """Return exactly 3 practice questions scaled to set_number difficulty."""

    @abstractmethod
    def grade_answer(
        self,
        question_text: str,
        criteria: str,
        answer: str,
        *,
        tool_result: "ToolResult | None" = None,
    ) -> GradedAnswer:
        """Grade one student answer and return is_correct + short feedback.

        When *tool_result* carries a definitive is_equivalent verdict, the LLM
        must use that verdict for is_correct and only generate aligned feedback.
        """

    @abstractmethod
    def grade_chat_answer(
        self, question_text: str, student_answer: str
    ) -> ChatAnswerGrade:
        """Grade a teaching-chat answer in isolation (question + answer only).

        Used when the deterministic math tool can't decide. is_correct is None
        when the student's message isn't an answer to grade.
        """

    @abstractmethod
    def generate_lesson_summary(
        self, ctx: TutorContext, total_correct: int, total_questions: int
    ) -> str:
        """Write a short final lesson summary after all practice sets are done."""
