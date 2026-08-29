"""What the homework tutor is told about where the student has got to.

The model cannot infer which exercises are done from the transcript, and an
exercise index past the end of the outline does not read as "finished" — told
neither, it sent a student back to an exercise they had already solved.
"""

from app.agent.schemas import HomeworkExercise, SessionState
from app.agent.teacher import TeacherAgent


def _outline(count: int = 3) -> list[HomeworkExercise]:
    return [
        HomeworkExercise(
            ref=f"exercise-{n}", text=f"Question {n}", target_type="exercise"
        )
        for n in range(1, count + 1)
    ]


def _system(state: SessionState, outline: list[HomeworkExercise]) -> str:
    return TeacherAgent().messages(
        state=state, outline=outline, history=[], student_text="ok"
    )[0].content


def test_solved_and_unsolved_exercises_are_both_named():
    state = SessionState(
        session_id=1,
        current_exercise_index=2,
        solved_refs=frozenset({"exercise-1"}),
    )

    system = _system(state, _outline())

    assert '"exercise-1"' in system.split("Skipped")[0].split("Solved:")[1]
    remaining = system.split("Not yet reached:")[1]
    assert '"exercise-2"' in remaining and '"exercise-3"' in remaining


def test_finishing_every_exercise_is_stated_outright():
    state = SessionState(
        session_id=1,
        current_exercise_index=4,
        solved_refs=frozenset({"exercise-1", "exercise-2", "exercise-3"}),
    )

    system = _system(state, _outline())

    assert "EVERY exercise in this homework is now solved" in system
    assert "Do not open another one" in system


def test_work_still_left_says_nothing_about_finishing():
    state = SessionState(
        session_id=1,
        current_exercise_index=2,
        solved_refs=frozenset({"exercise-1"}),
    )

    assert "EVERY exercise" not in _system(state, _outline())


def test_an_empty_outline_is_not_a_finished_one():
    """No worksheet parsed is not the same as a worksheet completed."""
    state = SessionState(session_id=1, current_exercise_index=1)

    assert "EVERY exercise" not in _system(state, [])
