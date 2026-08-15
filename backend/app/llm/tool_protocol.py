from __future__ import annotations

from collections.abc import Iterator
from typing import Protocol, runtime_checkable

from app.llm.tooling import AgentEvent, AssistantTurn, Msg, ToolSchema


@runtime_checkable
class ToolCallingLLM(Protocol):
    def complete_with_tools(
        self,
        messages: list[Msg],
        tools: list[ToolSchema],
        *,
        tool_choice: str | dict = "auto",
    ) -> AssistantTurn: ...

    def stream_with_tools(
        self,
        messages: list[Msg],
        tools: list[ToolSchema],
        *,
        tool_choice: str | dict = "auto",
    ) -> Iterator[AgentEvent]: ...
