import pytest

from app.core.enums import LessonPhase
from app.lesson.state import (
    CompletedState,
    InvalidLessonAction,
    PrePracticeExampleState,
    PracticeState,
    PracticeSummaryState,
    SummaryState,
    TeachingState,
    state_for_phase,
)


def test_transition_chain():
    assert isinstance(TeachingState().get_next_phase_state(None), PrePracticeExampleState)
    assert isinstance(
        PrePracticeExampleState().get_next_phase_state(None), PracticeState
    )
    assert isinstance(PracticeState().get_next_phase_state(None), PracticeSummaryState)
    assert isinstance(PracticeSummaryState().get_next_phase_state(None), SummaryState)
    assert isinstance(SummaryState().get_next_phase_state(None), CompletedState)


def test_completed_state_rejects_actions():
    state = CompletedState()
    with pytest.raises(InvalidLessonAction):
        state.get_next_phase_state(None)
    with pytest.raises(InvalidLessonAction):
        state.generate_reply_to_student_message(None, "hi")


def test_practice_state_blocks_chat():
    state = PracticeState()
    with pytest.raises(InvalidLessonAction):
        state.generate_reply_to_student_message(None, "hi")


def test_pre_practice_blocks_chat():
    state = PrePracticeExampleState()
    with pytest.raises(InvalidLessonAction):
        state.generate_reply_to_student_message(None, "hi")


def test_practice_summary_blocks_chat():
    state = PracticeSummaryState()
    with pytest.raises(InvalidLessonAction):
        state.generate_reply_to_student_message(None, "review")


def test_state_rehydration_from_phase():
    assert isinstance(state_for_phase(LessonPhase.TEACHING), TeachingState)
    assert isinstance(state_for_phase(LessonPhase.PRACTICE), PracticeState)
    assert isinstance(state_for_phase(LessonPhase.SUMMARY), SummaryState)
    assert isinstance(state_for_phase(LessonPhase.COMPLETED), CompletedState)


def test_unknown_phase_falls_back_to_completed():
    # Old sessions with deprecated phase values should not crash the app
    from app.lesson.state import state_for_phase as sfp
    result = sfp("explanation")  # type: ignore[arg-type]
    assert isinstance(result, CompletedState)
