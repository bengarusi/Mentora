from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from app.schemas.tutor import GeneratedQuestion, GradedAnswer, LevelAdjustment


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
    def generate_explanation(self, ctx: TutorContext) -> str: ...

    @abstractmethod
    def generate_example(self, ctx: TutorContext) -> str: ...

    @abstractmethod
    def chat_reply(self, ctx: TutorContext, student_message: str) -> str: ...

    @abstractmethod
    def generate_questions(self, ctx: TutorContext) -> list[GeneratedQuestion]:
        """Return exactly 3 questions of increasing difficulty (1, 2, 3)."""

    @abstractmethod
    def grade_answer(
        self, question_text: str, criteria: str, answer: str
    ) -> GradedAnswer: ...

    @abstractmethod
    def adjust_level(self, ctx: TutorContext, score: int) -> LevelAdjustment: ...

    @abstractmethod
    def summarize_session(self, ctx: TutorContext) -> str: ...
