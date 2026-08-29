"""Leaving an exercise for later, and being brought back to it.

A student stuck on exercise 2 of 6 should be able to move on and still be held
to it: skipped work is owed, not written off. The tutor collects the debt once
everything else has been reached, and when one skipped exercise is all that is
left it stops offering a way out.
"""

from app.agent.reducer import StateReducer
from app.agent.routing import wants_to_skip
from app.agent.schemas import (
    EvaluationResult,
    HomeworkExercise,
    ResponseTarget,
    SessionState,
)
from app.agent.teacher import TeacherAgent

REFS = tuple(f"exercise-{n}" for n in range(1, 7))


def _outline(count: int = 6) -> list[HomeworkExercise]:
    return [
        HomeworkExercise(ref=f"exercise-{n}", text=f"Question {n}")
        for n in range(1, count + 1)
    ]


def _system(state: SessionState, outline=None) -> str:
    return TeacherAgent().messages(
        state=state, outline=outline or _outline(), history=[], student_text="ok"
    )[0].content


# ---------------------------------------------------------------------------
# Recognising the request
# ---------------------------------------------------------------------------

def test_the_quick_action_and_its_plainer_phrasings_are_a_skip():
    for text in (
        "I'm ready for the next exercise.",
        "next question please",
        "skip this one",
        "can we move on?",
        "leave it for now",
        "אפשר לדלג?",
        "בוא נעבור לתרגיל הבא",
    ):
        assert wants_to_skip(text), text


def test_an_answer_is_not_a_skip():
    for text in ("3/4", "I think the answer is seven", "why is that?"):
        assert not wants_to_skip(text), text


# ---------------------------------------------------------------------------
# The transition
# ---------------------------------------------------------------------------

def test_skipping_parks_the_exercise_and_moves_to_the_next_untouched_one():
    state = SessionState(
        session_id=1,
        current_exercise_index=2,
        hint_level=3,
        awaiting_response=True,
        response_target=ResponseTarget("exercise-2", "exercise"),
        solved_refs=frozenset({"exercise-1"}),
    )

    after = StateReducer.skip(state, "exercise-2", REFS)

    assert after.skipped_refs == frozenset({"exercise-2"})
    assert after.solved_refs == frozenset({"exercise-1"})  # not solved by leaving
    assert after.current_exercise_index == 3
    assert after.hint_level == 0
    assert after.awaiting_response is False


def test_skipping_a_solved_exercise_changes_nothing():
    """Asking for the next one after getting it right is not a skip."""
    state = SessionState(
        session_id=1,
        current_exercise_index=1,
        solved_refs=frozenset({"exercise-1"}),
    )

    assert StateReducer.skip(state, "exercise-1", REFS) is state


def test_the_last_untouched_exercise_leads_back_to_the_parked_ones():
    state = SessionState(
        session_id=1,
        current_exercise_index=6,
        solved_refs=frozenset({"exercise-1", "exercise-3", "exercise-5"}),
        skipped_refs=frozenset({"exercise-2", "exercise-4"}),
    )

    after = StateReducer.skip(state, "exercise-6", REFS)

    assert after.skipped_refs == frozenset({"exercise-2", "exercise-4", "exercise-6"})
    assert after.current_exercise_index == 2  # the earliest one still owed


def test_solving_a_skipped_exercise_clears_the_debt():
    state = SessionState(
        session_id=1,
        current_exercise_index=2,
        awaiting_response=True,
        response_target=ResponseTarget("exercise-2", "exercise"),
        solved_refs=frozenset({"exercise-1", "exercise-3", "exercise-5", "exercise-6"}),
        skipped_refs=frozenset({"exercise-2", "exercise-4"}),
    )
    evaluation = EvaluationResult(
        verdict=True,
        authoritative=True,
        question_ref="exercise-2",
        target_type="exercise",
        tool_used="fraction_arithmetic",
    )

    after = StateReducer.reduce(
        state, evaluation, run_id="r", outline_refs=REFS
    ).next_state

    assert after.skipped_refs == frozenset({"exercise-4"})
    assert "exercise-2" in after.solved_refs
    assert after.current_exercise_index == 4  # straight on to the one still owed


# ---------------------------------------------------------------------------
# What the tutor is told to do about it
# ---------------------------------------------------------------------------

def test_with_work_still_untouched_nothing_is_said_about_going_back():
    state = SessionState(
        session_id=1,
        current_exercise_index=3,
        solved_refs=frozenset({"exercise-1"}),
        skipped_refs=frozenset({"exercise-2"}),
    )

    system = _system(state)

    assert "still owed" in system and '"exercise-2"' in system
    assert "would like to go back" not in system


def test_reaching_the_end_with_several_skipped_asks_which_to_return_to():
    state = SessionState(
        session_id=1,
        current_exercise_index=2,
        solved_refs=frozenset({"exercise-1", "exercise-3", "exercise-5", "exercise-6"}),
        skipped_refs=frozenset({"exercise-2", "exercise-4"}),
    )

    system = _system(state)

    assert "Ask which one they want to go back to" in system
    assert '"exercise-2", "exercise-4"' in system
    assert "one at a time" in system
    assert "Do not offer to stop or to move on" in system


def test_one_exercise_left_is_insisted_on():
    state = SessionState(
        session_id=1,
        current_exercise_index=4,
        solved_refs=frozenset(set(REFS) - {"exercise-4"}),
        skipped_refs=frozenset({"exercise-4"}),
    )

    system = _system(state)

    assert "Everything is done except exercise-4" in system
    assert "Do not offer to stop or to move on" in system
    assert "this is the only work left" in system


def test_everything_solved_still_reads_as_finished():
    state = SessionState(
        session_id=1,
        current_exercise_index=7,
        solved_refs=frozenset(REFS),
    )

    assert "EVERY exercise in this homework is now solved" in _system(state)


def test_the_exercise_to_ask_is_named_with_its_text():
    """The transcript argues for the exercise just left; the prompt must not."""
    state = SessionState(
        session_id=1,
        current_exercise_index=3,
        solved_refs=frozenset({"exercise-1"}),
        skipped_refs=frozenset({"exercise-2"}),
    )

    system = TeacherAgent().messages(
        state=state,
        outline=_outline(),
        history=[("tutor", "Question 2"), ("student", "next please")],
        student_text="next please",
        just_skipped="exercise-2",
    )[0].content

    assert 'The exercise to work on right now is exercise-3: "Question 3"' in system
    assert "exercise-2 is now PARKED" in system
    assert "do not tell them to finish it first" in system


def test_without_a_skip_nothing_is_said_about_parking():
    state = SessionState(session_id=1, current_exercise_index=1)

    assert "PARKED" not in _system(state)
