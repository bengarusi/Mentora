"""End-to-end regression coverage for the flag-gated Homework Tutor agent."""

import json

import pytest

from app.agent.schemas import ResponseTarget, SessionState
from app.agent.stores import SessionStateStore
from app.api.dependencies import get_llm, get_storage, get_voice_service
from app.core.config import settings
from app.files.storage import LocalFileStorage
from app.llm.tooling import AssistantTurn, PendingTarget, ToolCall
from app.main import app
from app.models.message import Message
from app.models.session import LessonSession
from app.models.student_mastery import StudentSkillMastery
from app.services.tutor_service import TutorService
from tests.conftest import auth_headers, make_student
from tests.scripted_agent_llm import ScriptedAgentLLM
from tests.test_speech_stream import FakeStreamingVoiceService


HOMEWORK = (
    "Exercise 1: What is 1/2 + 1/4?\n"
    "Exercise 2: Simplify 6/8.\n"
)


@pytest.fixture
def api(client, tmp_path):
    app.dependency_overrides[get_storage] = lambda: LocalFileStorage(tmp_path)
    yield client
    app.dependency_overrides.pop(get_storage, None)


def _prepare(api, llm):
    app.dependency_overrides[get_llm] = lambda: llm
    headers = auth_headers(api)
    session = api.post("/tutor/homework", json={"subject": "math"}, headers=headers).json()
    upload = api.post(
        f"/materials/homework/{session['id']}",
        files={"file": ("homework.txt", HOMEWORK.encode(), "text/plain")},
        headers=headers,
    )
    assert upload.status_code == 201
    analyze = api.post(f"/tutor/{session['id']}/homework/analyze", headers=headers)
    assert analyze.status_code == 200
    return headers, session


def _mark_substep_pending(session_factory, session_id):
    with session_factory() as db:
        store = SessionStateStore(db)
        state = store.load(session_id)
        store.save(
            state.__class__(
                **{
                    **state.__dict__,
                    "awaiting_response": True,
                    "response_target": ResponseTarget("exercise-1-step-1", "substep"),
                }
            )
        )
        db.commit()


def _script():
    return ScriptedAgentLLM(
        [
            AssistantTurn(
                content="Unverified intermediate speculation that must disappear.",
                tool_calls=(
                    ToolCall(
                        "eval-1",
                        "evaluateAnswer",
                        {"student_answer": "3/4", "question_ref": "exercise-1"},
                    ),
                ),
            ),
            AssistantTurn(
                content="Correct. Exercise 2: simplify 6/8. What do you notice?",
                pending_target=PendingTarget("exercise-2", "exercise"),
            ),
        ]
    )


def test_http_turn_advances_after_final_answer_to_pending_substep(
    api, session_factory, monkeypatch
):
    """A verified full answer advances even while a scaffolding sub-step is pending."""
    monkeypatch.setattr(settings, "AGENT_ENABLED_HOMEWORK", True)
    headers, session = _prepare(api, _script())
    _mark_substep_pending(session_factory, session["id"])

    response = api.post(
        f"/tutor/{session['id']}/turn",
        json={"content": "3/4", "turn_id": "http-turn-1"},
        headers=headers,
    )

    assert response.status_code == 200, response.text
    assert "intermediate speculation" not in response.json()["tutor_message"]
    with session_factory() as db:
        state = SessionStateStore(db).load(session["id"])
        assert state.current_exercise_index == 2
        assert state.hint_level == 0
        assert state.response_target == ResponseTarget("exercise-2", "exercise")


def test_speech_stream_interleaves_tool_events_but_never_intermediate_text(
    api, session_factory, monkeypatch
):
    monkeypatch.setattr(settings, "AGENT_ENABLED_HOMEWORK", True)
    headers, session = _prepare(api, _script())
    _mark_substep_pending(session_factory, session["id"])
    app.dependency_overrides[get_voice_service] = lambda: FakeStreamingVoiceService()

    response = api.post(
        f"/tutor/{session['id']}/turn/speech-stream",
        json={"content": "3/4", "turn_id": "speech-turn-1"},
        headers=headers,
    )
    events = [json.loads(line) for line in response.text.splitlines() if line]
    types = [event["type"] for event in events]
    text = "".join(event.get("data", "") for event in events if event["type"] == "text_delta")

    assert types[0] == "stream_start"
    assert types.count("tool_start") == 1
    assert types.count("tool_end") == 1
    assert types.count("done") == 1
    assert "intermediate speculation" not in text
    trace = api.get(f"/tutor/{session['id']}/agent-traces", headers=headers).json()
    assert "intermediate speculation" not in json.dumps(trace)


def test_agent_http_turn_requires_a_stable_client_turn_id(api, monkeypatch):
    monkeypatch.setattr(settings, "AGENT_ENABLED_HOMEWORK", True)
    headers, session = _prepare(api, _script())

    response = api.post(
        f"/tutor/{session['id']}/turn",
        json={"content": "3/4"},
        headers=headers,
    )

    assert response.status_code == 422


def test_dropped_text_stream_rolls_back_messages_and_learning_state(
    db_session, monkeypatch
):
    """Even a later accidental commit must not preserve a half-consumed turn."""
    monkeypatch.setattr(settings, "AGENT_ENABLED_HOMEWORK", True)
    student = make_student(db_session)
    session = LessonSession(
        student_id=student.id,
        subject="math",
        topic="Homework Help",
        subtopic="Fractions",
        goal_text="Finish homework",
        mode="homework",
        phase="homework_help",
        homework_outline=[
            {
                "ref": "exercise-1",
                "text": "Simplify 2/4",
                "expected_answer": "1/2",
            }
        ],
    )
    db_session.add(session)
    db_session.commit()
    SessionStateStore(db_session).save(
        SessionState(
            session_id=session.id,
            awaiting_response=True,
            response_target=ResponseTarget("exercise-1", "exercise"),
        )
    )
    db_session.commit()
    llm = ScriptedAgentLLM(
        [
            AssistantTurn(
                tool_calls=(
                    ToolCall(
                        "eval-1",
                        "evaluateAnswer",
                        {"student_answer": "ignored", "question_ref": "exercise-1"},
                    ),
                )
            ),
            AssistantTurn(content="Correct."),
        ]
    )
    stream = TutorService(
        db_session, llm, student
    ).stream_student_message_and_get_tutor_reply(
        session.id, "1/2", turn_id="turn-drop", ndjson_events=True
    )

    assert json.loads(next(stream))["type"] == "stream_start"
    assert json.loads(next(stream))["type"] == "tool_start"
    assert json.loads(next(stream))["type"] == "tool_end"
    stream.close()
    # Simulate accidental reuse of the request-scoped Session. The stream
    # boundary itself must already have removed every staged write.
    db_session.commit()
    db_session.expire_all()

    state = SessionStateStore(db_session).load(session.id)
    assert state.current_exercise_index == 1
    assert state.solved_refs == frozenset()
    assert db_session.query(StudentSkillMastery).count() == 0
    assert (
        db_session.query(Message).filter(Message.session_id == session.id).count()
        == 0
    )


def test_agent_progress_is_derived_from_reducer_state_not_llm(
    api, session_factory, monkeypatch
):
    class ProgressMustNotCallLLM(ScriptedAgentLLM):
        def summarize_homework_progress(self, *args, **kwargs):
            raise AssertionError("LLM must not determine authoritative agent progress")

    monkeypatch.setattr(settings, "AGENT_ENABLED_HOMEWORK", True)
    llm = ProgressMustNotCallLLM([])
    headers, session = _prepare(api, llm)
    with session_factory() as db:
        store = SessionStateStore(db)
        state = store.load(session["id"])
        store.save(
            SessionState(
                **{
                    **state.__dict__,
                    "current_exercise_index": 2,
                    "solved_refs": frozenset({"exercise-1", "invented-ref"}),
                }
            )
        )
        db.commit()

    progress = api.get(
        f"/tutor/{session['id']}/homework/progress", headers=headers
    )

    assert progress.status_code == 200
    assert progress.json() == {"total_exercises": 2, "solved_exercises": 1}


def test_chatting_with_no_exercise_left_uses_one_legacy_call_and_no_agent(
    db_session, monkeypatch
):
    """The cheap path still exists — for turns with nothing left to arm.

    While an exercise is unsolved and nothing is awaited, the agent has to run:
    it is the only thing that can ask the next exercise and mark it as awaited.
    Once the worksheet is finished, a conversational turn is just a conversation.
    """
    class CountingFastPathLLM(ScriptedAgentLLM):
        def __init__(self):
            super().__init__([])
            self.legacy_calls = 0
            self.agent_calls = 0

        def chat_reply(self, *args, **kwargs):
            self.legacy_calls += 1
            return super().chat_reply(*args, **kwargs)

        def stream_with_tools(self, *args, **kwargs):
            self.agent_calls += 1
            raise AssertionError("conversational fast path must skip the agent loop")

    monkeypatch.setattr(settings, "AGENT_ENABLED_HOMEWORK", True)
    student = make_student(db_session)
    session = LessonSession(
        student_id=student.id,
        subject="math",
        topic="Homework Help",
        subtopic="Fractions",
        goal_text="Finish",
        mode="homework",
        phase="homework_help",
        homework_outline=[{"ref": "exercise-1", "text": "Simplify 2/4"}],
    )
    db_session.add(session)
    db_session.commit()
    store = SessionStateStore(db_session)
    state = store.load(session.id)
    store.save(
        SessionState(
            **{**state.__dict__, "solved_refs": frozenset({"exercise-1"})}
        )
    )
    db_session.commit()
    llm = CountingFastPathLLM()

    result = TutorService(db_session, llm, student).send_student_message_and_get_tutor_reply(
        session.id, "hello there"
    )

    assert result.tutor_message
    assert llm.legacy_calls == 1
    assert llm.agent_calls == 0


def test_chatting_between_exercises_runs_the_agent(db_session, monkeypatch):
    """The turn that used to strand a session now reaches the agent."""

    class CountingAgentLLM(ScriptedAgentLLM):
        def __init__(self):
            super().__init__([AssistantTurn(content="Next up: what is 1/2 + 1/4?")])
            self.agent_calls = 0

        def stream_with_tools(self, *args, **kwargs):
            self.agent_calls += 1
            return super().stream_with_tools(*args, **kwargs)

    monkeypatch.setattr(settings, "AGENT_ENABLED_HOMEWORK", True)
    student = make_student(db_session, email="between@example.com")
    session = LessonSession(
        student_id=student.id,
        subject="math",
        topic="Homework Help",
        subtopic="Fractions",
        goal_text="Finish",
        mode="homework",
        phase="homework_help",
        homework_outline=[{"ref": "exercise-1", "text": "Simplify 2/4"}],
    )
    db_session.add(session)
    db_session.commit()
    llm = CountingAgentLLM()

    TutorService(db_session, llm, student).send_student_message_and_get_tutor_reply(
        session.id, "yes", turn_id="turn-between"
    )

    assert llm.agent_calls == 1
