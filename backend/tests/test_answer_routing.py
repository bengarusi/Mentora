import pytest

from app.agent.routing import might_need_tools, should_evaluate_answer
from app.agent.schemas import ResponseTarget, SessionState


@pytest.mark.parametrize(
    "text",
    [
        "I don't know",
        "give me a hint",
        "explain again",
        "just tell me",
        "next exercise",
        "thanks",
        "אני לא יודע",
        "תן לי רמז",
        "תסביר שוב",
        "תגיד לי את התשובה",
        "לשאלה הבאה",
        "תודה",
    ],
)
def test_explicit_non_answer_intent_vetoes_pending_answer_routing(text):
    state = SessionState(
        session_id=1,
        awaiting_response=True,
        response_target=ResponseTarget("exercise-1", "exercise"),
    )

    assert should_evaluate_answer(text, state) is False


def test_pending_response_target_drives_answer_routing_for_free_form_answers():
    state = SessionState(
        session_id=1,
        awaiting_response=True,
        response_target=ResponseTarget("exercise-1", "exercise"),
    )

    assert should_evaluate_answer("eighteen thirtieths because I cancelled by 6", state)


def test_numeric_parsing_alone_never_routes_an_answer():
    state = SessionState(session_id=1, awaiting_response=False)

    assert should_evaluate_answer("3/5", state) is False


# ---------------------------------------------------------------------------
# Which turns need the agent at all
# ---------------------------------------------------------------------------

_REFS = ("exercise-1", "exercise-2", "exercise-3")


def test_the_gap_between_exercises_belongs_to_the_agent():
    """Regression: one correct answer used to strand the rest of the session.

    Nothing is awaited right after a correct answer, so "yes" to "shall we do
    the next one?" took the chat path — which cannot arm a target, so no later
    answer was ever graded and the solved counter stopped at one.
    """
    state = SessionState(
        session_id=1,
        current_exercise_index=2,
        awaiting_response=False,
        solved_refs=frozenset({"exercise-1"}),
    )

    assert might_need_tools("yes", state, outline_refs=_REFS) is True


def test_a_pending_answer_still_routes_to_the_agent():
    state = SessionState(
        session_id=1,
        awaiting_response=True,
        response_target=ResponseTarget("exercise-1", "exercise"),
    )

    assert might_need_tools("3/4", state, outline_refs=_REFS) is True


def test_chatting_after_the_last_exercise_takes_the_cheap_path():
    state = SessionState(
        session_id=1,
        current_exercise_index=4,
        awaiting_response=False,
        solved_refs=frozenset(_REFS),
    )

    assert might_need_tools("that was fun", state, outline_refs=_REFS) is False


def test_a_non_answer_while_waiting_takes_the_cheap_path():
    state = SessionState(
        session_id=1,
        awaiting_response=True,
        response_target=ResponseTarget("exercise-1", "exercise"),
        solved_refs=frozenset(),
    )

    assert might_need_tools("thanks", state, outline_refs=_REFS) is False


def test_a_worksheet_that_parsed_to_nothing_always_needs_the_agent():
    state = SessionState(session_id=1, awaiting_response=False)

    assert might_need_tools("what do I do?", state, outline_refs=()) is True
