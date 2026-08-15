from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.math.schemas import ToolResult

from app.llm.provider import LLMProvider, TutorContext
from app.schemas.tutor import (
    ChatAnswerGrade,
    GeneratedPracticeQuestion,
    GradedAnswer,
)


class FakeLLMProvider(LLMProvider):
    """Deterministic in-memory provider for tests — no network, no cost.
    grade_answer marks an answer correct when it equals the question's correct_answer."""

    def __init__(self):
        # Recorded so tests can assert on what a prompt did and did not contain.
        self.board_prompts: list[tuple[str, str]] = []

    def generate_teaching_intro(self, ctx: TutorContext) -> str:
        return (
            f"Today we'll learn about {ctx.topic}. "
            f"Here is a quick example. Now, can you tell me: what is 1+1?"
        )

    def chat_reply(
        self,
        ctx: TutorContext,
        student_message: str,
        *,
        verification: "ToolResult | None" = None,
    ) -> str:
        if verification is not None and verification.is_equivalent is not None:
            verdict = "correct" if verification.is_equivalent else "incorrect"
            return f"Reply to: {student_message} [verdict={verdict}]"
        return f"Reply to: {student_message}"

    def chat_reply_stream(
        self,
        ctx: TutorContext,
        student_message: str,
        *,
        verification: "ToolResult | None" = None,
    ) -> Iterator[str]:
        for word in self.chat_reply(
            ctx, student_message, verification=verification
        ).split(" "):
            yield word + " "

    def generate_homework_intro(self, ctx: TutorContext) -> str:
        seen = "I can see your homework." if ctx.homework_text else "Please upload your homework."
        return f"Let's work on this together. {seen} What do you think it's asking?"

    def summarize_homework_progress(
        self,
        homework_text: str,
        transcript: list[tuple[str, str]],
        total_exercises: int,
    ) -> int:
        # Deterministic stand-in: count tutor turns that read as a
        # confirmation, capped to the real total.
        solved = sum(
            1
            for role, content in transcript
            if role == "tutor" and "correct" in content.lower()
        )
        return min(solved, total_exercises)

    def generate_difficulty_change_message(
        self, ctx: TutorContext, new_level: str
    ) -> str:
        return f"Switching to {new_level} for {ctx.topic}. Here is a new example. What is 2+2?"

    def generate_pre_practice_example(self, ctx: TutorContext) -> str:
        return (
            f"Example Question:\nSolve a sample {ctx.topic} problem.\n\n"
            f"Solution:\nStep 1: Identify the problem.\nStep 2: Apply the method.\n\n"
            f"Answer: sample-answer\n\n"
            f"What to remember: Always follow the steps.\n\n"
            f"Now you're ready to try similar questions yourself!"
        )

    def generate_practice_questions(
        self, ctx: TutorContext, set_number: int
    ) -> list[GeneratedPracticeQuestion]:
        base = (set_number - 1) * 3
        return [
            GeneratedPracticeQuestion(
                difficulty=i,
                question=f"Set {set_number} Q{i} about {ctx.topic}",
                correct_answer=f"correct{base + i}",
                solution_steps=f"Step 1: approach {i}. Answer: correct{base + i}.",
                explanation=f"Method explanation for difficulty {i}.",
            )
            for i in (1, 2, 3)
        ]

    def generate_board_explanation(self, system: str, user: str) -> dict:
        """A board that always passes validation.

        Steps are deliberately non-numeric so the chain check abstains: tests
        that care about validation build their own payloads, and everything else
        just needs a board that succeeds and can be narrated."""
        self.board_prompts.append((system, user))
        return {
            "title": "On the board",
            "intro": "Let's look at this together.",
            "blocks": [
                {
                    "kind": "steps",
                    "id": "s1",
                    "caption": "Working through the question",
                    "narration": "First we write down what we already know.",
                    "items": [
                        {"math": "a + b", "operation": "start with what we know"},
                        {"math": "a + b = c", "note": "keep both sides balanced"},
                    ],
                },
                {
                    "kind": "callout",
                    "id": "c1",
                    "caption": "A tip to remember",
                    "narration": "Remember, whatever you do to one side you do to the other.",
                    "tone": "insight",
                    "text": "Do the same thing to both sides.",
                },
            ],
        }

    def grade_answer(
        self,
        question_text: str,
        criteria: str,
        answer: str,
        *,
        tool_result: "ToolResult | None" = None,
    ) -> GradedAnswer:
        # If the deterministic tool gave a verdict, honour it exactly.
        if tool_result is not None and tool_result.is_equivalent is not None:
            is_correct = tool_result.is_equivalent
            return GradedAnswer(
                is_correct=is_correct,
                feedback="Correct! Great job!" if is_correct else "Not quite, try again.",
            )
        # Fallback: simple string comparison (no real LLM in tests).
        is_correct = answer.strip().lower() == criteria.strip().lower()
        return GradedAnswer(
            is_correct=is_correct,
            feedback="Well done!" if is_correct else "Not quite, try again.",
        )

    def grade_chat_answer(
        self, question_text: str, student_answer: str
    ) -> ChatAnswerGrade:
        # Deterministic stub: treat a reply containing "right" as correct, else
        # unknown. Real grading is exercised via the math tool in unit tests.
        if "right" in student_answer.lower():
            return ChatAnswerGrade(is_correct=True, correct_answer=student_answer)
        return ChatAnswerGrade(is_correct=None, correct_answer=None)

    def generate_lesson_summary(
        self, ctx: TutorContext, total_correct: int, total_questions: int
    ) -> str:
        return (
            f"You learned about {ctx.topic} today. "
            f"You answered {total_correct} out of {total_questions} correctly. "
            f"Keep up the great work!"
        )
