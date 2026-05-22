from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.math.schemas import ToolResult

from app.schemas.tutor import GeneratedPracticeQuestion, GradedAnswer


class LLMError(Exception):
    """Raised when the LLM provider fails (network, parsing, invalid output)."""


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


class LLMProvider(ABC):
    """Strategy interface. Concrete providers (OpenAI, fakes) implement these."""

    @abstractmethod
    def generate_teaching_intro(self, ctx: TutorContext) -> str:
        """Open the teaching phase: explain the topic with examples and invite questions."""

    @abstractmethod
    def chat_reply(self, ctx: TutorContext, student_message: str) -> str:
        """Respond to one student message during the teaching or summary phase."""

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
    def generate_lesson_summary(
        self, ctx: TutorContext, total_correct: int, total_questions: int
    ) -> str:
        """Write a short final lesson summary after all practice sets are done."""
