"""Behavioral tests for the authoritative, pure homework state reducer."""

from app.agent.reducer import StateReducer
from app.agent.schemas import EvaluationResult, ResponseTarget, SessionState


def _evaluation(
    *,
    verdict: bool,
    target_type: str = "exercise",
    question_ref: str = "exercise-1",
) -> EvaluationResult:
    return EvaluationResult(
        verdict=verdict,
        authoritative=True,
        question_ref=question_ref,
        target_type=target_type,
        skill="fractions",
        tool_used="fraction_arithmetic",
    )


def test_correct_full_exercise_advances_even_while_substep_was_pending():
    """Regression: a final answer must not be re-asked because a sub-step was pending."""
    state = SessionState(
        session_id=7,
        current_exercise_index=1,
        hint_level=2,
        awaiting_response=True,
        response_target=ResponseTarget("exercise-1-step-1", "substep"),
    )

    transition = StateReducer.reduce(state, _evaluation(verdict=True), run_id="run-1")

    assert transition.next_state.current_exercise_index == 2
    assert transition.next_state.hint_level == 0
    assert transition.next_state.awaiting_response is False
    assert transition.next_state.response_target is None
    assert transition.next_state.solved_refs == frozenset({"exercise-1"})
    assert transition.mastery_delta is not None
    assert transition.mastery_delta.correct is True


def test_correct_substep_stays_on_the_current_exercise():
    state = SessionState(
        session_id=7,
        current_exercise_index=3,
        hint_level=2,
        awaiting_response=True,
        response_target=ResponseTarget("exercise-3-step-1", "substep"),
    )

    transition = StateReducer.reduce(
        state,
        _evaluation(
            verdict=True,
            target_type="substep",
            question_ref="exercise-3-step-1",
        ),
        run_id="run-1",
    )

    assert transition.next_state.current_exercise_index == 3
    assert transition.next_state.hint_level == 0


def test_unregistered_substep_evaluation_cannot_change_state_or_mastery():
    state = SessionState(
        session_id=7,
        current_exercise_index=3,
        hint_level=2,
        awaiting_response=True,
        response_target=ResponseTarget("exercise-3-step-1", "substep"),
    )

    transition = StateReducer.reduce(
        state,
        _evaluation(
            verdict=True,
            target_type="substep",
            question_ref="exercise-3-made-up",
        ),
        run_id="turn-1",
    )

    assert transition.next_state == state
    assert transition.mastery_delta is None


def test_incorrect_answer_escalates_hint_and_retains_target():
    target = ResponseTarget("exercise-1", "exercise")
    state = SessionState(
        session_id=7,
        hint_level=1,
        awaiting_response=True,
        response_target=target,
    )

    transition = StateReducer.reduce(state, _evaluation(verdict=False), run_id="run-1")

    assert transition.next_state.hint_level == 2
    assert transition.next_state.response_target == target
    assert transition.mastery_delta is not None
    assert transition.mastery_delta.correct is False


def test_non_authoritative_evaluation_cannot_change_state_or_mastery():
    state = SessionState(session_id=7, hint_level=1)
    evaluation = EvaluationResult(
        verdict=True,
        authoritative=False,
        question_ref="exercise-1",
        target_type="exercise",
        tool_used="llm_fallback",
    )

    transition = StateReducer.reduce(state, evaluation, run_id="run-1")

    assert transition.next_state == state
    assert transition.mastery_delta is None


def test_replaying_same_run_and_question_is_idempotent():
    state = SessionState(session_id=7, current_exercise_index=1)
    first = StateReducer.reduce(state, _evaluation(verdict=True), run_id="run-1")
    replay = StateReducer.reduce(
        first.next_state, _evaluation(verdict=True), run_id="run-1"
    )

    assert replay.next_state.current_exercise_index == 2
    assert replay.mastery_delta is None


def test_already_solved_reference_cannot_advance_again_in_a_later_run():
    state = SessionState(
        session_id=7,
        current_exercise_index=1,
        solved_refs=frozenset({"exercise-1"}),
    )

    replay = StateReducer.reduce(state, _evaluation(verdict=True), run_id="run-2")

    assert replay.next_state == state
    assert replay.mastery_delta is None


def test_authoritative_result_for_a_different_exercise_cannot_move_current_state():
    state = SessionState(session_id=7, current_exercise_index=2)

    stale = StateReducer.reduce(state, _evaluation(verdict=True), run_id="run-2")

    assert stale.next_state == state
    assert stale.mastery_delta is None


def test_advancing_skips_an_exercise_already_solved_out_of_order():
    """A student who jumped ahead must not be walked back into finished work."""
    state = SessionState(
        session_id=7,
        current_exercise_index=1,
        awaiting_response=True,
        response_target=ResponseTarget("exercise-1", "exercise"),
        solved_refs=frozenset({"exercise-2", "exercise-3"}),
    )

    transition = StateReducer.reduce(state, _evaluation(verdict=True), run_id="run-1")

    assert transition.next_state.current_exercise_index == 4
    assert transition.next_state.solved_refs == frozenset(
        {"exercise-1", "exercise-2", "exercise-3"}
    )
