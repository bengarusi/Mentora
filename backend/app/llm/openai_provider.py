from __future__ import annotations

import json
import logging
import time
from collections.abc import Iterator
from typing import TYPE_CHECKING

from openai import OpenAI

from app.core.config import settings
from app.llm import prompts
from app.llm.provider import LLMError, LLMProvider, TutorContext
from app.schemas.tutor import ChatAnswerGrade, GeneratedPracticeQuestion, GradedAnswer

if TYPE_CHECKING:
    from app.math.schemas import ToolResult

log = logging.getLogger("app.llm.openai_provider")


class OpenAIProvider(LLMProvider):
    def __init__(self):
        if not settings.OPENAI_API_KEY:
            raise LLMError("OPENAI_API_KEY is not configured")
        # timeout + retries: a stalled call fails fast (with SDK backoff) rather
        # than hanging the UI indefinitely.
        self.client = OpenAI(
            api_key=settings.OPENAI_API_KEY, timeout=30.0, max_retries=2
        )
        self.model = settings.OPENAI_MODEL

    def _is_reasoning_model(self) -> bool:
        return "gpt-5" in (self.model or "")

    def _call_llm(
        self,
        system: str,
        user: str,
        json_mode: bool = False,
        *,
        operation: str = "llm_call",
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> str:
        # Metadata only — never log prompt/response text.
        start = time.perf_counter()
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
            if max_tokens is not None:
                if self._is_reasoning_model():
                    # gpt-5 uses max_completion_tokens (not max_tokens), and that
                    # budget covers internal reasoning tokens too — add a 1500-token
                    # buffer so reasoning doesn't consume the entire allowance.
                    kwargs["max_completion_tokens"] = max_tokens + 1500
                else:
                    kwargs["max_tokens"] = max_tokens
            if temperature is not None and not self._is_reasoning_model():
                kwargs["temperature"] = temperature
            response = self.client.chat.completions.create(**kwargs)
            content = response.choices[0].message.content or ""
            duration_ms = (time.perf_counter() - start) * 1000
            log.info(
                "llm call op=%s model=%s duration_ms=%.1f resp_chars=%d",
                operation,
                self.model,
                duration_ms,
                len(content),
            )
            return content
        except LLMError:
            raise
        except Exception as exc:
            duration_ms = (time.perf_counter() - start) * 1000
            log.error(
                "llm call failed op=%s model=%s duration_ms=%.1f error=%s",
                operation,
                self.model,
                duration_ms,
                exc,
            )
            raise LLMError(str(exc)) from exc

    def generate_teaching_intro(self, ctx: TutorContext) -> str:
        return self._call_llm(
            *prompts.teaching_intro_prompt(ctx),
            operation="teaching_intro",
            max_tokens=600,
            temperature=0.7,
        ).strip()

    def chat_reply(
        self,
        ctx: TutorContext,
        student_message: str,
        *,
        verification: "ToolResult | None" = None,
    ) -> str:
        return self._call_llm(
            *prompts.chat_prompt(ctx, student_message, verification=verification),
            operation="chat_reply",
            max_tokens=400,
            temperature=0.6,
        ).strip()

    def chat_reply_stream(
        self,
        ctx: TutorContext,
        student_message: str,
        *,
        verification: "ToolResult | None" = None,
    ) -> Iterator[str]:
        system, user = prompts.chat_prompt(
            ctx, student_message, verification=verification
        )
        start = time.perf_counter()
        log.info("llm stream start op=chat_reply_stream model=%s", self.model)
        try:
            token_kwarg = (
                {"max_completion_tokens": 400 + 1500}
                if self._is_reasoning_model()
                else {"max_tokens": 400, "temperature": 0.6}
            )
            stream = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                **token_kwarg,
                stream=True,
            )
            for chunk in stream:
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta
        except LLMError:
            raise
        except Exception as exc:
            log.error(
                "llm stream failed op=chat_reply_stream model=%s error=%s",
                self.model,
                exc,
            )
            raise LLMError(str(exc)) from exc
        duration_ms = (time.perf_counter() - start) * 1000
        log.info(
            "llm stream done op=chat_reply_stream model=%s duration_ms=%.1f",
            self.model,
            duration_ms,
        )

    def generate_difficulty_change_message(
        self, ctx: TutorContext, new_level: str
    ) -> str:
        return self._call_llm(
            *prompts.difficulty_change_prompt(ctx, new_level),
            operation="difficulty_change",
            max_tokens=500,
            temperature=0.7,
        ).strip()

    def generate_pre_practice_example(self, ctx: TutorContext) -> str:
        return self._call_llm(
            *prompts.pre_practice_example_prompt(ctx),
            operation="pre_practice_example",
            max_tokens=600,
            temperature=0.7,
        ).strip()

    def generate_practice_questions(
        self, ctx: TutorContext, set_number: int
    ) -> list[GeneratedPracticeQuestion]:
        system, user = prompts.practice_questions_prompt(ctx, set_number)
        raw = self._call_llm(
            system,
            user,
            json_mode=True,
            operation="practice_questions",
            max_tokens=800,
            temperature=0.7,
        )
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
        self,
        question_text: str,
        criteria: str,
        answer: str,
        *,
        tool_result: "ToolResult | None" = None,
    ) -> GradedAnswer:
        system, user = prompts.grade_prompt(
            question_text, criteria, answer, tool_result=tool_result
        )
        raw = self._call_llm(
            system,
            user,
            json_mode=True,
            operation="grade_answer",
            max_tokens=120,
            temperature=0.3,
        )
        try:
            data = json.loads(raw)
            return GradedAnswer(
                is_correct=data["is_correct"],
                feedback=data["feedback"],
            )
        except Exception as exc:
            raise LLMError(f"Could not parse grade JSON: {exc}") from exc

    def grade_chat_answer(
        self, question_text: str, student_answer: str
    ) -> ChatAnswerGrade:
        raw = self._call_llm(
            *prompts.chat_grade_prompt(question_text, student_answer),
            json_mode=True,
            operation="chat_grade",
            max_tokens=150,
            temperature=0.0,
        )
        try:
            data = json.loads(raw)
            return ChatAnswerGrade(
                is_correct=data.get("is_correct"),
                correct_answer=data.get("correct_answer"),
            )
        except Exception as exc:
            raise LLMError(f"Could not parse chat grade JSON: {exc}") from exc

    def generate_lesson_summary(
        self, ctx: TutorContext, total_correct: int, total_questions: int
    ) -> str:
        return self._call_llm(
            *prompts.lesson_summary_prompt(ctx, total_correct, total_questions),
            operation="lesson_summary",
            max_tokens=300,
            temperature=0.6,
        ).strip()
