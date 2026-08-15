from __future__ import annotations

from collections.abc import Iterator

from app.llm.tooling import AgentEvent, AssistantTurn, Msg, ToolSchema
from tests.fake_llm import FakeLLMProvider


class ScriptedAgentLLM(FakeLLMProvider):
    """Boundary fake: each call consumes one complete scripted assistant step."""

    def __init__(self, turns: list[AssistantTurn]):
        super().__init__()
        self.turns = list(turns)
        self.calls: list[dict] = []

    def complete_with_tools(
        self,
        messages: list[Msg],
        tools: list[ToolSchema],
        *,
        tool_choice: str | dict = "auto",
    ) -> AssistantTurn:
        self.calls.append({"messages": messages, "tools": tools, "tool_choice": tool_choice})
        return self.turns.pop(0)

    def stream_with_tools(
        self,
        messages: list[Msg],
        tools: list[ToolSchema],
        *,
        tool_choice: str | dict = "auto",
    ) -> Iterator[AgentEvent]:
        turn = self.complete_with_tools(messages, tools, tool_choice=tool_choice)
        if turn.content:
            midpoint = max(1, len(turn.content) // 2)
            yield AgentEvent.text_delta(turn.content[:midpoint])
            yield AgentEvent.text_delta(turn.content[midpoint:])
        yield AgentEvent.assistant_turn(turn)
