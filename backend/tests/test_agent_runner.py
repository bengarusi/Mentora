from app.agent.runner import AgentRunner
from app.agent.registry import ToolOutput
from app.agent.schemas import HomeworkExercise, ResponseTarget, SessionState
from app.agent.stores import SessionStateStore
from app.llm.tooling import AssistantTurn, PendingTarget, ToolCall
from app.models.agent_trace import AgentTrace
from app.models.session import LessonSession
from app.models.student_mastery import StudentSkillMastery
from tests.conftest import make_student
from tests.scripted_agent_llm import ScriptedAgentLLM

import time
from dataclasses import replace


def _session(db, student):
    row = LessonSession(
        student_id=student.id,
        subject="math",
        topic="Homework Help",
        subtopic="Fractions",
        goal_text="Finish homework",
        mode="homework",
        phase="homework_help",
        homework_outline=[
            {"ref": "exercise-1", "text": "Simplify 2/4", "expected_answer": "1/2"},
            {"ref": "exercise-2", "text": "What is 1/2 + 1/4?", "expected_answer": "3/4"},
        ],
    )
    db.add(row)
    db.commit()
    return row


def test_final_answer_while_substep_pending_advances_and_streams_only_final_text(db_session):
    """Regression: intermediate prose is dropped and verified exercise state advances."""
    student = make_student(db_session)
    session = _session(db_session, student)
    SessionStateStore(db_session).save(
        SessionState(
            session_id=session.id,
            awaiting_response=True,
            response_target=ResponseTarget("exercise-1-step-1", "substep"),
        )
    )
    llm = ScriptedAgentLLM(
        [
            AssistantTurn(
                content="I think that's probably right!",
                tool_calls=(
                    ToolCall(
                        "call-1",
                        "evaluateAnswer",
                        {"student_answer": "1/2", "question_ref": "exercise-1"},
                    ),
                ),
            ),
            AssistantTurn(
                content="Correct. Let's try exercise 2: what is 1/2 + 1/4?",
                pending_target=PendingTarget("exercise-2", "exercise"),
            ),
        ]
    )

    events = list(AgentRunner(db_session, llm, student, session).run_stream("1/2"))

    assert "I think" not in "".join(e.data or "" for e in events if e.type == "text_delta")
    assert "Correct. Let's try exercise 2" in "".join(
        e.data or "" for e in events if e.type == "text_delta"
    )
    assert [e.type for e in events if e.type.startswith("tool_")] == ["tool_start", "tool_end"]
    loaded = SessionStateStore(db_session).load(session.id)
    assert loaded.current_exercise_index == 2
    assert loaded.awaiting_response is True
    assert loaded.response_target == ResponseTarget("exercise-2", "exercise")


def test_full_exercise_answer_skips_model_tool_selection_round_trip(db_session):
    student = make_student(db_session)
    session = _session(db_session, student)
    SessionStateStore(db_session).save(
        SessionState(
            session_id=session.id,
            awaiting_response=True,
            response_target=ResponseTarget("exercise-1", "exercise"),
        )
    )
    llm = ScriptedAgentLLM(
        [
            AssistantTurn(
                content="Correct. Now try exercise 2.",
                pending_target=PendingTarget("exercise-2", "exercise"),
            )
        ]
    )

    events = list(
        AgentRunner(db_session, llm, student, session).run_stream(
            "1/2", turn_id="direct-eval"
        )
    )

    assert len(llm.calls) == 1
    assert [event.type for event in events] == [
        "tool_start",
        "tool_end",
        "text_delta",
    ]
    assert SessionStateStore(db_session).load(session.id).current_exercise_index == 2


def test_duplicate_calls_use_cached_observation_and_do_not_double_advance(db_session):
    student = make_student(db_session)
    session = _session(db_session, student)
    SessionStateStore(db_session).save(
        SessionState(
            session_id=session.id,
            awaiting_response=True,
            response_target=ResponseTarget("exercise-1", "exercise"),
        )
    )
    call = ToolCall(
        "call-1", "evaluateAnswer", {"student_answer": "1/2", "question_ref": "exercise-1"}
    )
    llm = ScriptedAgentLLM(
        [
            AssistantTurn(tool_calls=(call,)),
            AssistantTurn(tool_calls=(ToolCall("call-2", call.name, call.arguments),)),
            AssistantTurn(content="Correct — now continue."),
        ]
    )

    list(AgentRunner(db_session, llm, student, session).run_stream("1/2"))

    assert SessionStateStore(db_session).load(session.id).current_exercise_index == 2


def test_non_answer_intent_cannot_invoke_evaluation_or_advance_state(db_session):
    """A model cannot turn a request for help into fabricated learning evidence."""
    student = make_student(db_session)
    session = _session(db_session, student)
    SessionStateStore(db_session).save(
        SessionState(
            session_id=session.id,
            awaiting_response=True,
            response_target=ResponseTarget("exercise-1", "exercise"),
        )
    )
    llm = ScriptedAgentLLM(
        [
            AssistantTurn(
                tool_calls=(
                    ToolCall(
                        "fabricated",
                        "evaluateAnswer",
                        {
                            "student_answer": "1/2",
                            "question_ref": "exercise-1",
                        },
                    ),
                )
            ),
            AssistantTurn(content="Let's take one smaller step."),
        ]
    )

    list(AgentRunner(db_session, llm, student, session).run_stream("give me a hint"))

    state = SessionStateStore(db_session).load(session.id)
    assert state.current_exercise_index == 1
    assert state.solved_refs == frozenset()
    assert db_session.query(AgentTrace).filter(
        AgentTrace.kind == "state_transition"
    ).count() == 0
    exposed = {tool.name for tool in llm.calls[0]["tools"]}
    assert "evaluateAnswer" not in exposed


def test_retried_client_turn_cannot_increment_hint_or_mastery_twice(db_session):
    student = make_student(db_session)
    session = _session(db_session, student)
    SessionStateStore(db_session).save(
        SessionState(
            session_id=session.id,
            awaiting_response=True,
            response_target=ResponseTarget("exercise-1", "exercise"),
        )
    )

    def wrong_attempt():
        return ScriptedAgentLLM(
            [
                AssistantTurn(
                    tool_calls=(
                        ToolCall(
                            "eval",
                            "evaluateAnswer",
                            {
                                "student_answer": "model value is ignored",
                                "question_ref": "exercise-1",
                            },
                        ),
                    )
                ),
                AssistantTurn(
                    content="Try again.",
                    pending_target=PendingTarget("exercise-1", "exercise"),
                ),
            ]
        )

    first_llm = wrong_attempt()
    list(
        AgentRunner(db_session, first_llm, student, session).run_stream(
            "1/3", turn_id="client-turn-1"
        )
    )
    retry_llm = wrong_attempt()
    list(
        AgentRunner(db_session, retry_llm, student, session).run_stream(
            "1/3", turn_id="client-turn-1"
        )
    )

    state = SessionStateStore(db_session).load(session.id)
    mastery = db_session.query(StudentSkillMastery).one()
    assert state.hint_level == 1
    assert mastery.attempts == 1
    assert mastery.correct == 0
    assert retry_llm.calls == []


def test_retry_after_correct_advance_cannot_grade_the_next_exercise(db_session):
    student = make_student(db_session)
    session = _session(db_session, student)
    SessionStateStore(db_session).save(
        SessionState(
            session_id=session.id,
            awaiting_response=True,
            response_target=ResponseTarget("exercise-1", "exercise"),
        )
    )
    first = ScriptedAgentLLM(
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
            AssistantTurn(
                content="Now exercise 2.",
                pending_target=PendingTarget("exercise-2", "exercise"),
            ),
        ]
    )
    list(
        AgentRunner(db_session, first, student, session).run_stream(
            "1/2", turn_id="correct-turn"
        )
    )
    retry = ScriptedAgentLLM([])

    list(
        AgentRunner(db_session, retry, student, session).run_stream(
            "1/2", turn_id="correct-turn"
        )
    )

    state = SessionStateStore(db_session).load(session.id)
    mastery = db_session.query(StudentSkillMastery).one()
    assert state.current_exercise_index == 2
    assert state.hint_level == 0
    assert mastery.attempts == 1
    assert mastery.correct == 1
    assert retry.calls == []


def test_step_budget_forces_a_tools_disabled_final_call(db_session):
    student = make_student(db_session)
    session = _session(db_session, student)
    repeated = [
        AssistantTurn(tool_calls=(ToolCall(f"c-{i}", "analyzeHomework", {}),))
        for i in range(4)
    ]
    llm = ScriptedAgentLLM([*repeated, AssistantTurn(content="Let's continue together.")])

    list(AgentRunner(db_session, llm, student, session).run_stream("help"))

    assert llm.calls[-1]["tools"] == []
    assert db_session.query(AgentTrace).filter(AgentTrace.kind == "forced_final").count() == 1


def test_tool_schemas_never_expose_bound_identity_or_database_fields(db_session):
    student = make_student(db_session)
    session = _session(db_session, student)
    runner = AgentRunner(db_session, ScriptedAgentLLM([]), student, session)

    schema_text = str([schema.as_openai() for schema in runner.registry.schemas()])

    assert "student_id" not in schema_text
    assert "session_id" not in schema_text
    assert "\"db\"" not in schema_text


def test_provider_strips_structured_response_target_from_student_visible_text():
    from app.llm.openai_provider import OpenAIProvider

    visible, target = OpenAIProvider._parse_agent_content(
        'Try exercise 2 now. <response_target question_ref="exercise-2" target_type="exercise"/>'
    )

    assert visible == "Try exercise 2 now."
    assert target == PendingTarget("exercise-2", "exercise")


def test_provider_strips_control_tags_even_when_attributes_are_reordered():
    from app.llm.openai_provider import OpenAIProvider

    visible, target = OpenAIProvider._parse_agent_content(
        "Try this. <response_target target_type='substep' "
        "question_ref='exercise-1-step-1'/>"
    )

    assert visible == "Try this."
    assert target == PendingTarget("exercise-1-step-1", "substep")


def test_model_cannot_persist_a_nonexistent_substep_target(db_session):
    student = make_student(db_session)
    session = _session(db_session, student)
    llm = ScriptedAgentLLM(
        [
            AssistantTurn(
                content="Try this smaller step.",
                pending_target=PendingTarget(
                    "exercise-1-does-not-exist", "substep"
                ),
            )
        ]
    )

    list(AgentRunner(db_session, llm, student, session).run_stream("help"))

    state = SessionStateStore(db_session).load(session.id)
    assert state.awaiting_response is False
    assert state.response_target is None


def test_invalid_model_target_cannot_clear_an_existing_server_target(db_session):
    student = make_student(db_session)
    session = _session(db_session, student)
    expected = ResponseTarget("exercise-1", "exercise")
    SessionStateStore(db_session).save(
        SessionState(
            session_id=session.id,
            awaiting_response=True,
            response_target=expected,
        )
    )
    llm = ScriptedAgentLLM(
        [
            AssistantTurn(
                content="Try this.",
                pending_target=PendingTarget("exercise-999-step-42", "substep"),
            )
        ]
    )

    list(AgentRunner(db_session, llm, student, session).run_stream("help"))

    state = SessionStateStore(db_session).load(session.id)
    assert state.awaiting_response is True
    assert state.response_target == expected


def test_agent_traces_store_metadata_not_student_or_material_content(db_session):
    student = make_student(db_session)
    session = _session(db_session, student)
    SessionStateStore(db_session).save(
        SessionState(
            session_id=session.id,
            awaiting_response=True,
            response_target=ResponseTarget("exercise-1", "exercise"),
        )
    )
    llm = ScriptedAgentLLM(
        [
            AssistantTurn(
                tool_calls=(
                    ToolCall(
                        "eval-private",
                        "evaluateAnswer",
                        {
                            "student_answer": "model value",
                            "question_ref": "exercise-1",
                        },
                    ),
                )
            ),
            AssistantTurn(content="Correct."),
        ]
    )

    list(
        AgentRunner(db_session, llm, student, session).run_stream(
            "private reasoning gives 1/2"
        )
    )

    traces = db_session.query(AgentTrace).all()
    serialized = str(
        [(trace.args_json, trace.result_json) for trace in traces]
    ).lower()
    assert "private reasoning" not in serialized
    assert "student_answer" not in serialized
    assert "correct_answer" not in serialized
    assert "steps" not in serialized


def test_tool_timeout_returns_promptly_as_an_error_observation(
    db_session, monkeypatch
):
    from app.core.config import settings

    student = make_student(db_session)
    session = _session(db_session, student)
    runner = AgentRunner(db_session, ScriptedAgentLLM([]), student, session)
    definition = runner.registry._definitions["analyzeHomework"]

    def slow_handler(_args):
        time.sleep(0.2)
        return ToolOutput({"ok": True})

    runner.registry._definitions["analyzeHomework"] = replace(
        definition, handler=slow_handler
    )
    monkeypatch.setattr(settings, "AGENT_TOOL_TIMEOUT_S", 0.01)
    started = time.perf_counter()

    result = runner.registry.invoke(ToolCall("slow", "analyzeHomework", {}))

    assert time.perf_counter() - started < 0.1
    assert result.error == "tool_timeout"
    assert result.content == {"ok": False, "error": "tool_timeout"}


def test_analyze_homework_observation_contains_server_current_position(db_session):
    student = make_student(db_session)
    session = _session(db_session, student)
    SessionStateStore(db_session).save(
        SessionState(session_id=session.id, current_exercise_index=2)
    )
    llm = ScriptedAgentLLM(
        [
            AssistantTurn(
                tool_calls=(ToolCall("analyze", "analyzeHomework", {}),)
            ),
            AssistantTurn(content="Let's continue."),
        ]
    )

    list(AgentRunner(db_session, llm, student, session).run_stream("help"))

    tool_message = llm.calls[1]["messages"][-1]
    assert '"current_exercise_index": 2' in tool_message.content


def test_tool_failure_becomes_an_observation_and_loop_still_finishes(db_session):
    student = make_student(db_session)
    session = _session(db_session, student)
    llm = ScriptedAgentLLM(
        [
            AssistantTurn(
                tool_calls=(
                    ToolCall(
                        "bad-annotation",
                        "recordLearningAnnotation",
                        {"kind": "not-valid", "text": "ignored"},
                    ),
                )
            ),
            AssistantTurn(content="Let's continue without that note."),
        ]
    )

    text = AgentRunner(db_session, llm, student, session).run("help")

    assert text == "Let's continue without that note."
    tool_message = llm.calls[1]["messages"][-1]
    assert "invalid_arguments" in tool_message.content
    assert db_session.query(AgentTrace).filter(AgentTrace.kind == "error").count() == 1
