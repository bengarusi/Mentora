from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal


TargetType = Literal["exercise", "substep"]


@dataclass(frozen=True)
class ResponseTarget:
    question_ref: str
    target_type: TargetType


@dataclass(frozen=True)
class HomeworkExercise:
    ref: str
    text: str
    expected_answer: str | None = None
    target_type: TargetType = "exercise"
    skill: str | None = None


@dataclass(frozen=True)
class Annotation:
    kind: Literal["misconception", "note"]
    text: str
    skill: str | None = None
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    source: Literal["model"] = "model"


@dataclass(frozen=True)
class SessionState:
    session_id: int
    current_goal: str = ""
    current_exercise_index: int = 1
    awaiting_response: bool = False
    response_target: ResponseTarget | None = None
    hint_level: int = 0
    solved_refs: frozenset[str] = frozenset()
    annotations: tuple[Annotation, ...] = ()
    materials_used: tuple[int, ...] = ()
    recent_evaluations: tuple[dict, ...] = ()
    recommended_next_action: str = ""
    applied_evaluation_keys: frozenset[str] = frozenset()


@dataclass(frozen=True)
class EvaluationResult:
    verdict: bool | None
    authoritative: bool
    question_ref: str
    target_type: TargetType
    tool_used: str
    skill: str | None = None
    correct_answer: str | None = None
    steps: tuple[str, ...] = ()
    steps_visible_to_student: bool = False
    reason: str | None = None

    def as_observation(self, state_after: SessionState | None = None) -> dict:
        verdict = (
            "correct" if self.verdict is True else "incorrect" if self.verdict is False else "undetermined"
        )
        hide_solution = self.verdict is False and not self.steps_visible_to_student
        data: dict = {
            "verdict": verdict,
            "authoritative": self.authoritative,
            "question_ref": self.question_ref,
            "target_type": self.target_type,
            "tool_used": self.tool_used,
            "steps_visible_to_student": self.steps_visible_to_student,
            "reason": self.reason,
        }
        # Omit solution-bearing fields entirely for incorrect attempts. Even
        # empty placeholders unnecessarily advertise hidden answer material to
        # the conversational model.
        if not hide_solution:
            data["correct_answer"] = self.correct_answer
            data["steps"] = list(self.steps)
        if self.authoritative and self.verdict is not None:
            data["instruction"] = (
                f"You MUST treat this as {'correct' if self.verdict else 'incorrect'}. "
                "Do not re-grade it."
            )
        else:
            # Nothing was established, and saying "correct" here is worse than
            # saying nothing: the server records no progress for an unconfirmed
            # answer, so the student is congratulated and then left on the same
            # exercise with the counter unmoved.
            data["instruction"] = (
                "This answer could NOT be checked. Do not tell the student whether they "
                "are right or wrong. Ask them to send the answer on its own, as a number."
            )
        if state_after is not None:
            data["state_after"] = {
                "current_exercise_index": state_after.current_exercise_index,
                "hint_level": state_after.hint_level,
                "awaiting_response": state_after.awaiting_response,
            }
        return data


@dataclass(frozen=True)
class MasteryDelta:
    skill: str | None
    correct: bool


@dataclass(frozen=True)
class StateTransition:
    next_state: SessionState
    mastery_delta: MasteryDelta | None
