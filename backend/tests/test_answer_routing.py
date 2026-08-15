import pytest

from app.agent.routing import should_evaluate_answer
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
