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


@pytest.mark.parametrize(
    "text",
    [
        # The apostrophe is what broke this: a student typed "i dont know",
        # the pattern required "don't", so the plea was force-graded as a math
        # answer and answered with "please send just your answer as a number".
        "i dont know",
        "i dont know help",
        "I DONT KNOW",
        "i don’t know",  # curly apostrophe from a phone keyboard
        "idk",
        "i dunno",
        "no idea",
        "no clue",
        "help",
        "help me",
        "i need help",
        "can you help me?",
        "Can you help me with question 2?",
        "Could I get some guidance?",
        "Can you walk me through this?",
        "im stuck",
        "i'm stuck",
        "i am confused",
        "i cant do it",
        "how do i do this",
        "what do i do",
        "Give me a hint",
        "Explain the method",
        "לא יודע",
        "אין לי מושג",
        "תעזור לי",
        "נתקעתי",
        "לא הבנתי",
    ],
)
def test_natural_pleas_for_help_are_never_graded_as_answers(text):
    """A student asking for help must not reach the math grader.

    The grader cannot parse a number out of prose, so it answered every plea
    with "please send just your answer as a number" — an unbreakable loop for a
    student who genuinely did not know.
    """
    state = SessionState(
        session_id=1,
        awaiting_response=True,
        response_target=ResponseTarget("exercise-1", "exercise"),
    )

    assert should_evaluate_answer(text, state) is False


@pytest.mark.parametrize(
    "text",
    [
        "56",
        "8 x 7 = 56",
        "the answer is 56",
        "56, but i needed help with it",
        "fifty six",
        "i think its 56",
        "3/4",
        "0.75",
    ],
)
def test_an_answer_is_still_graded_however_it_is_padded(text):
    """The widened help patterns must not swallow a real attempt: a message
    carrying a number is an answer even when it also mentions help."""
    state = SessionState(
        session_id=1,
        awaiting_response=True,
        response_target=ResponseTarget("exercise-1", "exercise"),
    )

    assert should_evaluate_answer(text, state) is True


@pytest.mark.parametrize(
    "text",
    [
        "i dont know",
        "idk",
        "no idea",
        "im stuck",
        "i cant do it",
        "Explain the method",
        "לא יודע",
        "נתקעתי",
        "אין לי מושג",
    ],
)
def test_every_plea_for_help_reaches_the_agent_not_the_cheap_path(text):
    """Only an agent turn climbs the help ladder.

    A narrower help list once sent these to the fast chat path, which cannot
    raise the hint level — so the student got the same rung, and so the same
    words, back for as long as they kept asking. The two lists are now read from
    the same place so they cannot drift apart again.
    """
    state = SessionState(
        session_id=1,
        current_exercise_index=1,
        awaiting_response=True,
        response_target=ResponseTarget("exercise-1", "exercise"),
    )

    assert might_need_tools(
        text, state, outline_refs=["exercise-1", "exercise-2"]
    ) is True
