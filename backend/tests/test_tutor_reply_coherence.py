"""User-visible safeguards for tutor replies after a verified wrong answer."""

import json

from app.api.dependencies import get_llm, get_voice_service
from app.main import app
from tests.conftest import auth_headers
from tests.fake_llm import FakeLLMProvider


class AnswerLeakingLLM(FakeLLMProvider):
    def generate_teaching_intro(self, ctx):
        return "Let's try one: what is 2 + 2?"

    def generate_difficulty_change_message(self, ctx, new_level):
        return "Let's try one: what is 2 + 2?"

    def chat_reply(self, ctx, student_message, *, verification=None):
        assert verification is not None and verification.is_equivalent is False
        return "Not quite — 2 + 2 = 4. Try again: what is 2 + 2?"

    def chat_reply_stream(self, ctx, student_message, *, verification=None):
        yield from self.chat_reply(
            ctx, student_message, verification=verification
        ).splitlines(keepends=True)


class PreviouslyRevealedLLM(AnswerLeakingLLM):
    def generate_teaching_intro(self, ctx):
        return "In this worked example, 2 + 2 = 4. What is 2 + 2?"

    def generate_difficulty_change_message(self, ctx, new_level):
        return "In this worked example, 2 + 2 = 4. What is 2 + 2?"

    def chat_reply(self, ctx, student_message, *, verification=None):
        assert verification is not None and verification.is_equivalent is False
        return "Try once more: what is 2 + 2?"


class SelfAnsweringNextQuestionLLM(AnswerLeakingLLM):
    def chat_reply(self, ctx, student_message, *, verification=None):
        assert verification is not None and verification.is_equivalent is True
        return "Correct! Next, 3 + 3 = 6. What is 3 + 3?"


def _lesson_waiting_for_two_plus_two(client, headers):
    session = client.post(
        "/sessions/",
        json={
            "subject": "math",
            "topic": "Addition & Subtraction",
            "subtopic": "Addition basics",
            "goal_text": "Learn addition",
        },
        headers=headers,
    ).json()
    opened = client.post(
        f"/tutor/{session['id']}/difficulty",
        json={"level": "easy"},
        headers=headers,
    )
    assert opened.status_code == 200
    return session


def test_final_tutor_turn_cannot_reveal_the_verified_answer_then_ask_for_it(client):
    app.dependency_overrides[get_llm] = lambda: AnswerLeakingLLM()
    headers = auth_headers(client)
    session = _lesson_waiting_for_two_plus_two(client, headers)

    response = client.post(
        f"/tutor/{session['id']}/turn",
        json={"content": "5"},
        headers=headers,
    )

    assert response.status_code == 200, response.text
    reply = response.json()["tutor_message"]
    assert "= 4" not in reply
    assert not ("4" in reply and "2 + 2?" in reply)


def test_an_answer_already_revealed_is_not_requested_again(client):
    app.dependency_overrides[get_llm] = lambda: PreviouslyRevealedLLM()
    headers = auth_headers(client)
    session = _lesson_waiting_for_two_plus_two(client, headers)

    response = client.post(
        f"/tutor/{session['id']}/turn",
        json={"content": "5"},
        headers=headers,
    )

    reply = response.json()["tutor_message"]
    assert "already established" in reply
    assert "what is 2 + 2" not in reply.lower()
    assert "Which step" in reply


def test_correct_turn_cannot_answer_its_own_next_question(client):
    app.dependency_overrides[get_llm] = lambda: SelfAnsweringNextQuestionLLM()
    headers = auth_headers(client)
    session = _lesson_waiting_for_two_plus_two(client, headers)

    response = client.post(
        f"/tutor/{session['id']}/turn",
        json={"content": "4"},
        headers=headers,
    )

    assert response.status_code == 200, response.text
    reply = response.json()["tutor_message"]
    assert "3 + 3 = 6" not in reply
    assert "what is 3 + 3" not in reply.lower()


def test_text_stream_does_not_emit_a_self_answered_next_question(client):
    app.dependency_overrides[get_llm] = lambda: SelfAnsweringNextQuestionLLM()
    headers = auth_headers(client)
    session = _lesson_waiting_for_two_plus_two(client, headers)

    response = client.post(
        f"/tutor/{session['id']}/turn/stream",
        json={"content": "4"},
        headers={**headers, "Accept": "application/x-ndjson"},
    )

    assert response.status_code == 200, response.text
    events = [json.loads(line) for line in response.text.splitlines() if line]
    reply = "".join(
        event["data"] for event in events if event["type"] == "text_delta"
    )
    assert "3 + 3 = 6" not in reply
    assert "what is 3 + 3" not in reply.lower()


def test_text_stream_never_emits_a_verified_answer_leak(client):
    app.dependency_overrides[get_llm] = lambda: AnswerLeakingLLM()
    headers = auth_headers(client)
    session = _lesson_waiting_for_two_plus_two(client, headers)

    response = client.post(
        f"/tutor/{session['id']}/turn/stream",
        json={"content": "5"},
        headers={**headers, "Accept": "application/x-ndjson"},
    )

    assert response.status_code == 200, response.text
    events = [json.loads(line) for line in response.text.splitlines() if line]
    reply = "".join(
        event["data"] for event in events if event["type"] == "text_delta"
    )
    assert "= 4" not in reply
    assert [event["type"] for event in events].count("done") == 1


def test_speech_stream_speaks_the_guarded_reply_once(client):
    spoken: list[str] = []

    class RecordingVoice:
        def iter_speech_audio(self, text):
            spoken.append(text)
            yield b"fake-mp3"

    app.dependency_overrides[get_llm] = lambda: AnswerLeakingLLM()
    app.dependency_overrides[get_voice_service] = lambda: RecordingVoice()
    headers = auth_headers(client)
    session = _lesson_waiting_for_two_plus_two(client, headers)

    response = client.post(
        f"/tutor/{session['id']}/turn/speech-stream",
        json={"content": "5"},
        headers=headers,
    )

    assert response.status_code == 200, response.text
    events = [json.loads(line) for line in response.text.splitlines() if line]
    reply = "".join(
        event["data"] for event in events if event["type"] == "text_delta"
    )
    assert "= 4" not in reply
    assert spoken
    assert "= 4" not in " ".join(spoken)
    assert [event["type"] for event in events].count("done") == 1


def test_coherence_guard_catches_the_screenshot_fraction_in_latex():
    from app.lesson.reply_policy import ensure_incorrect_reply_is_coherent
    from app.math.schemas import ToolResult

    reply = ensure_incorrect_reply_is_coherent(
        r"Not quite: 25/100 = **\frac{1}{4}**. What is it in simplest form?",
        ToolResult(
            success=True,
            tool_used="fraction_arithmetic",
            canonical_answer="1/4",
            is_equivalent=False,
        ),
        [],
    )

    assert "frac{1}{4}" not in reply
    assert "1/4" not in reply


def test_coherence_guard_catches_equivalent_decimal_and_spoken_answer_leaks():
    from app.lesson.reply_policy import ensure_incorrect_reply_is_coherent
    from app.math.schemas import ToolResult

    verdict = ToolResult(
        success=True,
        tool_used="fraction_arithmetic",
        canonical_answer="1/4",
        is_equivalent=False,
    )
    history = [("tutor", "Simplify 25/100."), ("student", "3/4")]

    for leak in (
        "Remember, 0.25 is the result. What is the simplest fraction?",
        "It is one quarter. What fraction do you get?",
    ):
        assert ensure_incorrect_reply_is_coherent(leak, verdict, history) != leak


def test_coherence_guard_allows_repeating_the_given_equivalent_value():
    from app.lesson.reply_policy import ensure_incorrect_reply_is_coherent
    from app.math.schemas import ToolResult

    prompt = "Start with the given 25/100. Which common factor could you use?"
    reply = ensure_incorrect_reply_is_coherent(
        prompt,
        ToolResult(
            success=True,
            tool_used="fraction_arithmetic",
            canonical_answer="1/4",
            is_equivalent=False,
        ),
        [("tutor", "Simplify 25/100."), ("student", "3/4")],
    )

    assert reply == prompt


def test_coherence_guard_does_not_mistake_an_operand_for_the_answer():
    from app.lesson.reply_policy import ensure_incorrect_reply_is_coherent
    from app.math.schemas import ToolResult

    hint = "Look at 4/2 and choose the operation. What should you do first?"
    reply = ensure_incorrect_reply_is_coherent(
        hint,
        ToolResult(
            success=True,
            tool_used="fraction_arithmetic",
            canonical_answer="2",
            is_equivalent=False,
        ),
        [],
    )

    assert reply == hint


def test_coherence_guard_allows_a_worked_example_before_a_fresh_question():
    from app.lesson.reply_policy import ensure_tutor_reply_is_coherent
    from app.math.schemas import ToolResult

    prompt = "For example, 2 + 2 = 4. Now, what is 3 + 3?"
    reply = ensure_tutor_reply_is_coherent(
        prompt,
        ToolResult(
            success=True,
            tool_used="chat_arithmetic",
            canonical_answer="4",
            is_equivalent=True,
        ),
        [],
    )

    assert reply == prompt
