from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Iterator
from typing import TYPE_CHECKING

from openai import OpenAI

from app.core.config import settings
from app.llm import prompts
from app.llm.provider import LLMError, LLMProvider, TutorContext
from app.llm.tooling import (
    AgentEvent,
    AssistantTurn,
    Msg,
    PendingTarget,
    ToolCall,
    ToolSchema,
)
from app.schemas.tutor import ChatAnswerGrade, GeneratedPracticeQuestion, GradedAnswer

if TYPE_CHECKING:
    from app.math.schemas import ToolResult

log = logging.getLogger("app.llm.openai_provider")


class OpenAIProvider(LLMProvider):
    _RESPONSE_TARGET = re.compile(r"<response_target\b[^>]*?/\s*>", re.IGNORECASE)
    _CONTROL_ATTRIBUTE = re.compile(
        r"([a-z_]+)\s*=\s*(['\"])(.*?)\2", re.IGNORECASE
    )

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

    def _agent_token_budget(self) -> dict[str, int]:
        # Tool calls and the requested concise final reply do not need an
        # unbounded completion. Reasoning models count hidden reasoning in the
        # same budget, matching the existing provider policy below.
        return (
            {"max_completion_tokens": 2100}
            if self._is_reasoning_model()
            else {"max_tokens": 600}
        )

    @staticmethod
    def _tool_messages(messages: list[Msg]) -> list[dict]:
        serialized: list[dict] = []
        for message in messages:
            item: dict = {"role": message.role, "content": message.content or None}
            if message.tool_calls:
                item["tool_calls"] = [
                    {
                        "id": call.id,
                        "type": "function",
                        "function": {
                            "name": call.name,
                            "arguments": json.dumps(call.arguments, ensure_ascii=False),
                        },
                    }
                    for call in message.tool_calls
                ]
            if message.tool_call_id:
                item["tool_call_id"] = message.tool_call_id
            serialized.append(item)
        return serialized

    @classmethod
    def _parse_agent_content(cls, content: str) -> tuple[str, PendingTarget | None]:
        matches = list(cls._RESPONSE_TARGET.finditer(content))
        pending = None
        for match in matches:
            attrs = {
                item.group(1).lower(): item.group(3)
                for item in cls._CONTROL_ATTRIBUTE.finditer(match.group(0))
            }
            target_type = attrs.get("target_type", "").lower()
            question_ref = attrs.get("question_ref")
            if question_ref and target_type in {"exercise", "substep"}:
                pending = PendingTarget(question_ref, target_type)
        visible = cls._RESPONSE_TARGET.sub("", content).strip()
        return visible, pending

    def complete_with_tools(
        self,
        messages: list[Msg],
        tools: list[ToolSchema],
        *,
        tool_choice: str | dict = "auto",
    ) -> AssistantTurn:
        started = time.perf_counter()
        try:
            kwargs = {
                "model": self.model,
                "messages": self._tool_messages(messages),
                **self._agent_token_budget(),
            }
            if tools:
                kwargs["tools"] = [tool.as_openai() for tool in tools]
                kwargs["tool_choice"] = tool_choice
            response = self.client.chat.completions.create(**kwargs)
            message = response.choices[0].message
            calls = tuple(
                ToolCall(
                    call.id,
                    call.function.name,
                    json.loads(call.function.arguments or "{}"),
                )
                for call in (message.tool_calls or [])
            )
            visible, pending = self._parse_agent_content(message.content or "")
            log.info(
                "llm agent call done model=%s duration_ms=%.1f tool_calls=%d resp_chars=%d",
                self.model,
                (time.perf_counter() - started) * 1000,
                len(calls),
                len(visible),
            )
            return AssistantTurn(visible, calls, pending)
        except Exception as exc:
            log.error(
                "llm agent call failed model=%s duration_ms=%.1f error=%s",
                self.model,
                (time.perf_counter() - started) * 1000,
                type(exc).__name__,
            )
            raise LLMError(str(exc)) from exc

    def stream_with_tools(
        self,
        messages: list[Msg],
        tools: list[ToolSchema],
        *,
        tool_choice: str | dict = "auto",
    ):
        started = time.perf_counter()
        first_delta_ms: float | None = None
        try:
            kwargs = {
                "model": self.model,
                "messages": self._tool_messages(messages),
                "stream": True,
                **self._agent_token_budget(),
            }
            if tools:
                kwargs["tools"] = [tool.as_openai() for tool in tools]
                kwargs["tool_choice"] = tool_choice
            stream = self.client.chat.completions.create(**kwargs)
            calls: dict[int, dict] = {}
            content: list[str] = []
            for chunk in stream:
                delta = chunk.choices[0].delta
                if delta.content:
                    if first_delta_ms is None:
                        first_delta_ms = (time.perf_counter() - started) * 1000
                    content.append(delta.content)
                    yield AgentEvent.text_delta(delta.content)
                for call in delta.tool_calls or []:
                    current = calls.setdefault(call.index, {"id": "", "name": "", "arguments": ""})
                    if call.id:
                        current["id"] = call.id
                    if call.function:
                        if call.function.name:
                            current["name"] += call.function.name
                        if call.function.arguments:
                            current["arguments"] += call.function.arguments
            tool_calls = tuple(
                ToolCall(item["id"], item["name"], json.loads(item["arguments"] or "{}"))
                for _, item in sorted(calls.items())
            )
            visible, pending = self._parse_agent_content("".join(content))
            log.info(
                "llm agent stream done model=%s duration_ms=%.1f first_delta_ms=%s "
                "tool_calls=%d resp_chars=%d",
                self.model,
                (time.perf_counter() - started) * 1000,
                round(first_delta_ms, 1) if first_delta_ms is not None else None,
                len(tool_calls),
                len(visible),
            )
            yield AgentEvent.assistant_turn(AssistantTurn(visible, tool_calls, pending))
        except Exception as exc:
            log.error(
                "llm agent stream failed model=%s duration_ms=%.1f error=%s",
                self.model,
                (time.perf_counter() - started) * 1000,
                type(exc).__name__,
            )
            raise LLMError(str(exc)) from exc

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

    def generate_homework_intro(self, ctx: TutorContext) -> str:
        return self._call_llm(
            *prompts.homework_intro_prompt(ctx),
            operation="homework_intro",
            max_tokens=600,
            temperature=0.6,
        ).strip()

    def summarize_homework_progress(
        self,
        homework_text: str,
        transcript: list[tuple[str, str]],
        total_exercises: int,
    ) -> int:
        raw = self._call_llm(
            *prompts.homework_progress_prompt(
                homework_text, transcript, total_exercises
            ),
            json_mode=True,
            operation="homework_progress",
            max_tokens=100,
            temperature=0.0,
        )
        try:
            solved = int(json.loads(raw)["solved_exercises"])
        except Exception as exc:
            raise LLMError(f"Could not parse homework progress JSON: {exc}") from exc
        return max(0, min(solved, total_exercises))

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
