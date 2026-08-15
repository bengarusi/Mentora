from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class Msg:
    role: Literal["system", "user", "assistant", "tool"]
    content: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
    tool_call_id: str | None = None


@dataclass(frozen=True)
class ToolSchema:
    name: str
    description: str
    parameters: dict[str, Any]

    def as_openai(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


@dataclass(frozen=True)
class AssistantTurn:
    content: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
    pending_target: PendingTarget | None = None


@dataclass(frozen=True)
class PendingTarget:
    question_ref: str
    target_type: Literal["exercise", "substep"]


@dataclass(frozen=True)
class AgentEvent:
    kind: Literal["text_delta", "assistant_turn"]
    text: str = ""
    assistant: AssistantTurn | None = None

    @classmethod
    def text_delta(cls, text: str) -> "AgentEvent":
        return cls("text_delta", text=text)

    @classmethod
    def assistant_turn(cls, turn: AssistantTurn) -> "AgentEvent":
        return cls("assistant_turn", assistant=turn)


@dataclass(frozen=True)
class AgentStreamEvent:
    type: Literal["text_delta", "tool_start", "tool_end"]
    data: str | None = None
    tool_name: str | None = None
    status: str | None = None
