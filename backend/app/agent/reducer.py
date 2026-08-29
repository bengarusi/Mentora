from __future__ import annotations

from dataclasses import replace

from app.agent.schemas import (
    Annotation,
    EvaluationResult,
    MasteryDelta,
    ResponseTarget,
    SessionState,
    StateTransition,
)


def _next_unsolved_index(current: int, solved: frozenset[str] | set[str]) -> int:
    """The next exercise still to do, skipping any already solved.

    A plain +1 walks back into work the student has finished whenever they solve
    something out of order. Running past the end of the outline is the intended
    "nothing left" signal — the prompt layer reads it from the refs, not from
    this number, so no bound is needed here.
    """
    index = current + 1
    while f"exercise-{index}" in solved:
        index += 1
    return index


class StateReducer:
    """Sole authority for homework-agent transitions; all methods are pure."""

    @staticmethod
    def reduce(
        state: SessionState,
        ev: EvaluationResult,
        *,
        run_id: str,
        max_hint_level: int = 4,
    ) -> StateTransition:
        if not ev.authoritative or ev.verdict is None:
            return StateTransition(state, None)

        current_ref = f"exercise-{state.current_exercise_index}"
        target_matches_current = ev.question_ref == current_ref
        if ev.target_type == "substep":
            # Substeps are server-issued capabilities: only the exact target
            # currently awaited by the session may affect authoritative state.
            # A shared exercise prefix is not sufficient because the model may
            # invent arbitrary suffixes.
            target_matches_current = bool(
                state.awaiting_response
                and state.response_target is not None
                and state.response_target.target_type == "substep"
                and ev.question_ref == state.response_target.question_ref
            )
        if not target_matches_current:
            return StateTransition(state, None)

        # A stale model/tool retry from a later HTTP turn cannot turn evidence
        # for an already solved exercise into another index/mastery update.
        if ev.question_ref in state.solved_refs:
            return StateTransition(state, None)

        key = f"{run_id}:{ev.question_ref}"
        if key in state.applied_evaluation_keys:
            return StateTransition(state, None)

        applied = state.applied_evaluation_keys | {key}
        recent = (*state.recent_evaluations[-9:], {
            "ref": ev.question_ref,
            "verdict": ev.verdict,
            "tool_used": ev.tool_used,
        })
        if ev.verdict:
            common = {
                "hint_level": 0,
                "awaiting_response": False,
                "response_target": None,
                "recent_evaluations": recent,
                "applied_evaluation_keys": applied,
            }
            if ev.target_type == "exercise":
                solved = state.solved_refs | {ev.question_ref}
                next_state = replace(
                    state,
                    current_exercise_index=_next_unsolved_index(
                        state.current_exercise_index, solved
                    ),
                    solved_refs=solved,
                    **common,
                )
            else:
                next_state = replace(state, **common)
        else:
            next_state = replace(
                state,
                hint_level=min(state.hint_level + 1, max_hint_level),
                recent_evaluations=recent,
                applied_evaluation_keys=applied,
            )
        return StateTransition(next_state, MasteryDelta(ev.skill, ev.verdict))

    @staticmethod
    def set_pending(
        state: SessionState, target: ResponseTarget | None
    ) -> SessionState:
        return replace(
            state,
            awaiting_response=target is not None,
            response_target=target,
        )

    @staticmethod
    def annotate(state: SessionState, annotation: Annotation) -> SessionState:
        return replace(state, annotations=(*state.annotations[-19:], annotation))
