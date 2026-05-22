import pytest

from app.core.enums import LessonPhase, SuccessLevel
from app.lesson.state import (
    AssessmentState,
    CompletedState,
    CorrectionState,
    ExampleState,
    ExplanationState,
    InvalidLessonAction,
    LevelAdjustmentState,
    state_for_phase,
)


def test_transition_chain():
    assert isinstance(ExplanationState().get_next_phase_state(None), ExampleState)
    assert isinstance(ExampleState().get_next_phase_state(None), AssessmentState)
    assert isinstance(
        CorrectionState().get_next_phase_state(None), LevelAdjustmentState
    )
    assert isinstance(
        LevelAdjustmentState().get_next_phase_state(None), CompletedState
    )


def test_completed_state_rejects_actions():
    state = CompletedState()
    with pytest.raises(InvalidLessonAction):
        state.get_next_phase_state(None)
    with pytest.raises(InvalidLessonAction):
        state.generate_reply_to_student_message(None, "hi")


def test_assessment_state_blocks_chat_and_advance():
    state = AssessmentState()
    with pytest.raises(InvalidLessonAction):
        state.generate_reply_to_student_message(None, "hi")
    with pytest.raises(InvalidLessonAction):
        state.get_next_phase_state(None)


def test_success_level_mapping():
    f = AssessmentState.determine_success_level_from_score
    assert f(3) == SuccessLevel.ACHIEVED
    assert f(2) == SuccessLevel.PARTIALLY
    assert f(1) == SuccessLevel.PARTIALLY
    assert f(0) == SuccessLevel.NOT_ACHIEVED


def test_state_rehydration_from_phase():
    assert isinstance(state_for_phase(LessonPhase.EXPLANATION), ExplanationState)
    assert isinstance(state_for_phase(LessonPhase.ASSESSMENT), AssessmentState)
    assert isinstance(state_for_phase(LessonPhase.COMPLETED), CompletedState)
