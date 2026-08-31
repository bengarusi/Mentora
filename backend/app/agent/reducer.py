from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace

from app.agent.schemas import (
    Annotation,
    EvaluationResult,
    MasteryDelta,
    ResponseTarget,
    SessionState,
    StateTransition,
)


def _next_index_to_offer(
    current: int,
    solved: frozenset[str] | set[str],
    skipped: frozenset[str] | set[str] = frozenset(),
    outline_refs: Sequence[str] = (),
) -> int:
    """Which exercise the student should be pointed at next.

    Untouched work first, in the order it appears on the worksheet. Only when
    there is none left does the parked work come back around — that is what
    makes a skip a postponement rather than a write-off. Running past the end of
    the outline is the "nothing at all left" signal; the prompt layer reads that
    from the refs rather than from this number.

    Without an outline this degrades to walking forward off the current index,
    which is all the older callers ever had.
    """
    if outline_refs:
        for index, ref in enumerate(outline_refs, start=1):
            if ref not in solved and ref not in skipped:
                return index
        for index, ref in enumerate(outline_refs, start=1):
            if ref in skipped:
                return index
        return len(outline_refs) + 1

    index = current + 1
    while f"exercise-{index}" in solved or f"exercise-{index}" in skipped:
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
        outline_refs: Sequence[str] = (),
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
                # Solving something that had been parked settles the debt.
                skipped = state.skipped_refs - {ev.question_ref}
                next_state = replace(
                    state,
                    current_exercise_index=_next_index_to_offer(
                        state.current_exercise_index, solved, skipped, outline_refs
                    ),
                    solved_refs=solved,
                    skipped_refs=skipped,
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
    def escalate_help(state: SessionState, *, max_hint_level: int = 4) -> SessionState:
        """Move one rung up the help ladder because the student asked for help.

        Only a wrong graded answer used to raise the hint level, so a student who
        kept asking for help — never answering, so never graded — stayed on rung
        zero and got the same reply every time. Asking again is itself the signal
        that the last help was too big a step. No mastery is touched: asking for
        help is not evidence about a skill.
        """
        return replace(
            state, hint_level=min(state.hint_level + 1, max_hint_level)
        )

    @staticmethod
    def skip(
        state: SessionState, ref: str, outline_refs: Sequence[str] = ()
    ) -> SessionState:
        """Park the exercise the student wants to leave and move them on.

        No mastery is recorded either way: giving up on a question is not
        evidence that it was answered wrongly, only that it was not answered.
        Solved work is never parked — asking for the next exercise after getting
        one right is just asking for the next exercise.
        """
        if ref in state.solved_refs:
            return state
        skipped = state.skipped_refs | {ref}
        return replace(
            state,
            skipped_refs=skipped,
            current_exercise_index=_next_index_to_offer(
                state.current_exercise_index, state.solved_refs, skipped, outline_refs
            ),
            hint_level=0,
            awaiting_response=False,
            response_target=None,
        )

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
