from app.llm.provider import LLMProvider, TutorContext
from app.schemas.tutor import GeneratedQuestion, GradedAnswer, LevelAdjustment


class FakeLLMProvider(LLMProvider):
    """Deterministic in-memory provider for tests — no network, no cost.
    grade_answer marks an answer correct when it equals the question's criteria,
    so tests can drive an exact score."""

    def generate_explanation(self, ctx: TutorContext) -> str:
        return f"Explanation about {ctx.topic}."

    def generate_example(self, ctx: TutorContext) -> str:
        return f"Example about {ctx.topic}."

    def chat_reply(self, ctx: TutorContext, student_message: str) -> str:
        return f"Reply to: {student_message}"

    def generate_questions(self, ctx: TutorContext) -> list[GeneratedQuestion]:
        return [
            GeneratedQuestion(
                difficulty=i,
                question=f"Question {i} about {ctx.topic}",
                criteria=f"correct{i}",
            )
            for i in (1, 2, 3)
        ]

    def grade_answer(
        self, question_text: str, criteria: str, answer: str
    ) -> GradedAnswer:
        is_correct = answer.strip().lower() == criteria.strip().lower()
        return GradedAnswer(
            is_correct=is_correct,
            feedback="Well done!" if is_correct else "Not quite, try again.",
        )

    def adjust_level(self, ctx: TutorContext, score: int) -> LevelAdjustment:
        return LevelAdjustment(direction="same", note=f"You scored {score}/3.")

    def summarize_session(self, ctx: TutorContext) -> str:
        return f"Summary of the lesson on {ctx.topic}."
