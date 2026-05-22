import json

from openai import OpenAI

from app.core.config import settings
from app.llm import prompts
from app.llm.provider import LLMError, LLMProvider, TutorContext
from app.schemas.tutor import GeneratedPracticeQuestion, GradedAnswer


class OpenAIProvider(LLMProvider):
    def __init__(self):
        if not settings.OPENAI_API_KEY:
            raise LLMError("OPENAI_API_KEY is not configured")
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)
        self.model = settings.OPENAI_MODEL

    def _call_llm(self, system: str, user: str, json_mode: bool = False) -> str:
        try:
            kwargs: dict = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            }
            if json_mode:
                kwargs["response_format"] = {"type": "json_object"}
            response = self.client.chat.completions.create(**kwargs)
            return response.choices[0].message.content or ""
        except LLMError:
            raise
        except Exception as exc:
            raise LLMError(str(exc)) from exc

    def generate_teaching_intro(self, ctx: TutorContext) -> str:
        return self._call_llm(*prompts.teaching_intro_prompt(ctx)).strip()

    def chat_reply(self, ctx: TutorContext, student_message: str) -> str:
        return self._call_llm(*prompts.chat_prompt(ctx, student_message)).strip()

    def generate_pre_practice_example(self, ctx: TutorContext) -> str:
        return self._call_llm(*prompts.pre_practice_example_prompt(ctx)).strip()

    def generate_practice_questions(
        self, ctx: TutorContext, set_number: int
    ) -> list[GeneratedPracticeQuestion]:
        system, user = prompts.practice_questions_prompt(ctx, set_number)
        raw = self._call_llm(system, user, json_mode=True)
        try:
            data = json.loads(raw)
            questions = [GeneratedPracticeQuestion(**q) for q in data["questions"]]
        except Exception as exc:
            raise LLMError(f"Could not parse practice questions JSON: {exc}") from exc
        if len(questions) != 3:
            raise LLMError(f"Expected 3 practice questions, got {len(questions)}")
        questions.sort(key=lambda q: q.difficulty)
        return questions

    def grade_answer(
        self, question_text: str, criteria: str, answer: str
    ) -> GradedAnswer:
        system, user = prompts.grade_prompt(question_text, criteria, answer)
        raw = self._call_llm(system, user, json_mode=True)
        try:
            data = json.loads(raw)
            return GradedAnswer(
                is_correct=data["is_correct"],
                feedback=data["feedback"],
            )
        except Exception as exc:
            raise LLMError(f"Could not parse grade JSON: {exc}") from exc

    def generate_lesson_summary(
        self, ctx: TutorContext, total_correct: int, total_questions: int
    ) -> str:
        return self._call_llm(
            *prompts.lesson_summary_prompt(ctx, total_correct, total_questions)
        ).strip()
