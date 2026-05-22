import json

from openai import OpenAI

from app.core.config import settings
from app.llm import prompts
from app.llm.provider import LLMError, LLMProvider, TutorContext
from app.schemas.tutor import GeneratedQuestion, GradedAnswer, LevelAdjustment


class OpenAIProvider(LLMProvider):
    def __init__(self):
        if not settings.OPENAI_API_KEY:
            raise LLMError("OPENAI_API_KEY is not configured")
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)
        self.model = settings.OPENAI_MODEL

    def _call_llm(self, system: str, user: str, json_mode: bool = False) -> str:
        try:
            kwargs = {
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
        except Exception as exc:  # network, auth, rate limit, etc.
            raise LLMError(str(exc)) from exc

    def generate_explanation(self, ctx: TutorContext) -> str:
        return self._call_llm(*prompts.explanation_prompt(ctx)).strip()

    def generate_example(self, ctx: TutorContext) -> str:
        return self._call_llm(*prompts.example_prompt(ctx)).strip()

    def chat_reply(self, ctx: TutorContext, student_message: str) -> str:
        return self._call_llm(*prompts.chat_prompt(ctx, student_message)).strip()

    def generate_questions(self, ctx: TutorContext) -> list[GeneratedQuestion]:
        system, user = prompts.questions_prompt(ctx)
        raw = self._call_llm(system, user, json_mode=True)
        try:
            data = json.loads(raw)
            questions = [GeneratedQuestion(**q) for q in data["questions"]]
        except Exception as exc:
            raise LLMError(f"Could not parse questions JSON: {exc}") from exc
        if len(questions) != 3:
            raise LLMError(f"Expected 3 questions, got {len(questions)}")
        questions.sort(key=lambda q: q.difficulty)
        return questions

    def grade_answer(
        self, question_text: str, criteria: str, answer: str
    ) -> GradedAnswer:
        system, user = prompts.grade_prompt(question_text, criteria, answer)
        raw = self._call_llm(system, user, json_mode=True)
        try:
            return GradedAnswer(**json.loads(raw))
        except Exception as exc:
            raise LLMError(f"Could not parse grade JSON: {exc}") from exc

    def adjust_level(self, ctx: TutorContext, score: int) -> LevelAdjustment:
        system, user = prompts.adjust_prompt(ctx, score)
        raw = self._call_llm(system, user, json_mode=True)
        try:
            return LevelAdjustment(**json.loads(raw))
        except Exception as exc:
            raise LLMError(f"Could not parse adjustment JSON: {exc}") from exc

    def summarize_session(self, ctx: TutorContext) -> str:
        return self._call_llm(*prompts.summary_prompt(ctx)).strip()
