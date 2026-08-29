from __future__ import annotations

import json
import logging
import re
from uuid import uuid4

from sqlalchemy.orm import Session

from app.agent.reducer import StateReducer
from app.agent.registry import ToolOutput, ToolRegistry, canonical_call_key, outline_from_json
from app.agent.routing import should_evaluate_answer, wants_to_skip
from app.agent.stores import AgentTraceStore, SessionStateStore, StudentProgressStore
from app.agent.teacher import TeacherAgent
from app.core.config import settings
from app.llm.tool_protocol import ToolCallingLLM
from app.llm.tooling import AgentStreamEvent, AssistantTurn, Msg, ToolCall
from app.models.message import Message
from app.models.session import LessonSession
from app.models.student import Student

log = logging.getLogger("app.agent.runner")
_SAFE_QUESTION_REF = re.compile(r"^exercise-\d+(?:-step-\d+)?$")


class AgentRunner:
    """Runs tool steps and orchestrates reducer → stores. Never commits."""

    def __init__(
        self,
        db: Session,
        llm: ToolCallingLLM,
        student: Student,
        session: LessonSession,
    ):
        self.db = db
        self.llm = llm
        self.student = student
        self.session = session
        self.teacher = TeacherAgent()
        self.registry = ToolRegistry(db, llm, student, session)  # type: ignore[arg-type]
        self.session_store = SessionStateStore(db)
        self.progress_store = StudentProgressStore(db)
        self.trace_store = AgentTraceStore(db)

    def _history(self) -> list[tuple[str, str]]:
        rows = (
            self.db.query(Message)
            .filter(Message.session_id == self.session.id)
            .order_by(Message.id.desc())
            .limit(10)
            .all()
        )
        rows.reverse()
        return [(row.role, row.content) for row in rows]

    def run(self, student_text: str, *, turn_id: str | None = None) -> str:
        return "".join(
            event.data or ""
            for event in self.run_stream(student_text, turn_id=turn_id)
            if event.type == "text_delta"
        ).strip()

    def run_stream(self, student_text: str, *, turn_id: str | None = None):
        run_id = str(uuid4())
        evaluation_run_id = turn_id or run_id
        # Serialise evidence application for this homework session. Together
        # with the stable client turn id this prevents concurrent retries from
        # producing duplicate state/mastery projections on PostgreSQL.
        state = self.session_store.load(self.session.id, for_update=True)
        outline = outline_from_json(self.session.homework_outline)
        history = self._history()
        # The phase saves the student's message before entering the runner so
        # the transaction remains message-atomic. Do not add it twice to the
        # real message array.
        if history and history[-1] == ("student", student_text):
            history = history[:-1]
        if turn_id and any(
            key.rsplit(":", 1)[0] == turn_id
            for key in state.applied_evaluation_keys
        ):
            # The authoritative portion of this client turn was already
            # committed. Do not ask the model again: after a correct result the
            # current target may have advanced, and re-routing the same payload
            # could otherwise create fresh evidence for the next exercise.
            previous_reply = next(
                (content for role, content in reversed(history) if role == "tutor"),
                None,
            )
            if previous_reply:
                yield AgentStreamEvent("text_delta", data=previous_reply)
            return

        # Leaving an exercise for later is a state change, so the server makes
        # it — the model is told what happened, not asked to agree to it. Doing
        # it here rather than through a tool keeps the student's "next one
        # please" from depending on the model recognising the phrasing.
        outline_refs = [item.ref for item in outline]
        if wants_to_skip(student_text):
            current_ref = (
                outline_refs[state.current_exercise_index - 1]
                if 0 <= state.current_exercise_index - 1 < len(outline_refs)
                else None
            )
            if current_ref and current_ref not in state.solved_refs:
                before = state
                state = StateReducer.skip(state, current_ref, outline_refs)
                self.session_store.save(state)
                self.trace_store.add(
                    run_id=run_id,
                    session_id=self.session.id,
                    step=0,
                    kind="state_transition",
                    tool_name="skipExercise",
                    result_json={
                        "before": self._state_summary(before),
                        "after": self._state_summary(state),
                    },
                )

        messages = self.teacher.messages(
            state=state,
            outline=outline,
            history=history,
            student_text=student_text,
        )
        seen: dict[tuple[str, str], ToolOutput] = {}
        forced = should_evaluate_answer(student_text, state)
        exposed_tools = tuple(
            name
            for name in self.teacher.exposed_tools
            if forced or name != "evaluateAnswer"
        )
        schemas = self.registry.schemas(exposed_tools)
        allowed_tools = frozenset(exposed_tools)
        direct_target = (
            state.response_target
            if forced
            and state.response_target is not None
            and state.response_target.target_type == "exercise"
            else None
        )
        post_evaluation_tools = tuple(
            name for name in exposed_tools if name != "evaluateAnswer"
        )
        post_evaluation_schemas = self.registry.schemas(post_evaluation_tools)
        post_evaluation_allowed = frozenset(post_evaluation_tools)
        step_budget = settings.AGENT_MAX_STEPS

        for step in range(step_budget):
            if direct_target is not None and step > 0:
                active_schemas = post_evaluation_schemas
                active_allowed_tools = post_evaluation_allowed
            else:
                active_schemas = schemas
                active_allowed_tools = allowed_tools
            choice: str | dict = (
                {"type": "function", "function": {"name": "evaluateAnswer"}}
                if forced and direct_target is None and step == 0
                else "auto"
            )
            buffered: list[str] = []
            if direct_target is not None and step == 0:
                # For a full-exercise target the server already owns the exact
                # question reference. Calling the model merely to repeat
                # evaluateAnswer adds a round trip and no useful judgment.
                turn = AssistantTurn(
                    tool_calls=(
                        ToolCall(
                            f"server-evaluation-{run_id}",
                            "evaluateAnswer",
                            {
                                "student_answer": student_text,
                                "question_ref": direct_target.question_ref,
                            },
                        ),
                    )
                )
            else:
                turn = AssistantTurn()
                for event in self.llm.stream_with_tools(
                    messages, active_schemas, tool_choice=choice
                ):
                    if event.kind == "text_delta":
                        buffered.append(event.text)
                    elif event.assistant is not None:
                        turn = event.assistant

            if not turn.tool_calls:
                final = turn.content or "".join(buffered)
                if final:
                    yield AgentStreamEvent("text_delta", data=final)
                state = self._record_pending(state, outline, turn.pending_target)
                self.session_store.save(state)
                return

            if buffered:
                log.info(
                    "dropped intermediate agent text run_id=%s step=%d chars=%d",
                    run_id,
                    step,
                    sum(map(len, buffered)),
                )
            messages.append(Msg("assistant", "", tool_calls=turn.tool_calls))
            for original_call in turn.tool_calls:
                call = original_call
                if call.name == "evaluateAnswer":
                    call = ToolCall(
                        call.id,
                        call.name,
                        {**call.arguments, "student_answer": student_text},
                    )
                yield AgentStreamEvent("tool_start", tool_name=call.name, status="running")
                key = canonical_call_key(call)
                repeated = key in seen
                output = seen.get(key)
                if output is None:
                    self.registry.bind_state(state)
                    output = (
                        self.registry.invoke(call)
                        if call.name in active_allowed_tools
                        else ToolOutput(
                            {"ok": False, "error": "tool_not_allowed_for_turn"},
                            error="tool_not_allowed_for_turn",
                        )
                    )
                seen[key] = output
                content = dict(output.content)
                if repeated:
                    content["note"] = "repeat call; cached observation"

                before = state
                if output.evaluation and output.evaluation.authoritative:
                    transition = StateReducer.reduce(
                        state,
                        output.evaluation,
                        run_id=evaluation_run_id,
                        max_hint_level=settings.AGENT_MAX_HINT_LEVEL,
                        outline_refs=outline_refs,
                    )
                    state = transition.next_state
                    self.session_store.save(state)
                    if transition.mastery_delta is not None:
                        self.progress_store.apply(
                            student_id=self.student.id,
                            subject=self.session.subject,
                            topic=self.session.topic,
                            delta=transition.mastery_delta,
                        )
                    content = output.evaluation.as_observation(state)
                    self.trace_store.add(
                        run_id=run_id,
                        session_id=self.session.id,
                        step=step,
                        kind="state_transition",
                        tool_name=call.name,
                        result_json={"before": self._state_summary(before), "after": self._state_summary(state)},
                    )
                if output.annotation:
                    state = StateReducer.annotate(state, output.annotation)
                    self.session_store.save(state)

                self.trace_store.add(
                    run_id=run_id,
                    session_id=self.session.id,
                    step=step,
                    kind="error" if output.error else "tool_call",
                    tool_name=call.name,
                    args_json=self._trace_args(call),
                    result_json=self._trace_result(content),
                    duration_ms=output.duration_ms,
                    error=output.error,
                )
                messages.append(Msg("tool", json.dumps(content, ensure_ascii=False), tool_call_id=call.id))
                yield AgentStreamEvent(
                    "tool_end",
                    tool_name=call.name,
                    status="error" if output.error else "complete",
                )
            self.db.flush()

        self.trace_store.add(
            run_id=run_id,
            session_id=self.session.id,
            step=step_budget,
            kind="forced_final",
        )
        buffered = []
        turn = AssistantTurn()
        for event in self.llm.stream_with_tools(messages, [], tool_choice="none"):
            if event.kind == "text_delta":
                buffered.append(event.text)
            elif event.assistant is not None:
                turn = event.assistant
        final = turn.content or "".join(buffered)
        if final:
            yield AgentStreamEvent("text_delta", data=final)
        state = self._record_pending(state, outline, turn.pending_target)
        self.session_store.save(state)

    @staticmethod
    def _state_summary(state):
        return {
            "current_exercise_index": state.current_exercise_index,
            "hint_level": state.hint_level,
            "awaiting_response": state.awaiting_response,
            "response_target": (
                {
                    "question_ref": state.response_target.question_ref,
                    "target_type": state.response_target.target_type,
                }
                if state.response_target
                else None
            ),
        }

    @staticmethod
    def _trace_args(call: ToolCall) -> dict:
        """Allow-list operational metadata; never persist student/tool prose."""
        result: dict = {}
        question_ref = call.arguments.get("question_ref")
        if isinstance(question_ref, str) and _SAFE_QUESTION_REF.fullmatch(question_ref):
            result["question_ref"] = question_ref
        if isinstance(call.arguments.get("limit"), int):
            result["limit"] = call.arguments["limit"]
        return result

    @staticmethod
    def _trace_result(content: dict) -> dict:
        """Keep verdict/timing observability without answers or retrieved text."""
        safe_keys = (
            "ok",
            "error",
            "verdict",
            "authoritative",
            "question_ref",
            "target_type",
            "tool_used",
            "total",
            "note",
        )
        result = {key: content[key] for key in safe_keys if key in content}
        question_ref = result.get("question_ref")
        if not (
            isinstance(question_ref, str)
            and _SAFE_QUESTION_REF.fullmatch(question_ref)
        ):
            result.pop("question_ref", None)
        if isinstance(content.get("results"), list):
            result["result_count"] = len(content["results"])
        if isinstance(content.get("exercises"), list):
            result["exercise_count"] = len(content["exercises"])
        if isinstance(content.get("state_after"), dict):
            result["state_after"] = {
                key: content["state_after"].get(key)
                for key in (
                    "current_exercise_index",
                    "hint_level",
                    "awaiting_response",
                )
            }
        return result

    @staticmethod
    def _record_pending(state, outline, declared_target):
        if declared_target is None:
            return StateReducer.set_pending(state, None)

        from app.agent.schemas import ResponseTarget

        current_index = state.current_exercise_index - 1
        current_ref = (
            outline[current_index].ref
            if 0 <= current_index < len(outline)
            else None
        )
        if declared_target.target_type == "exercise":
            valid = declared_target.question_ref == current_ref
        else:
            # The model may propose that it is awaiting a substep, but it
            # cannot mint an arbitrary state-changing identifier. The only
            # valid virtual substep for this turn is derived by the server
            # from the current exercise and hint progression.
            expected_substep_ref = (
                f"{current_ref}-step-{max(1, state.hint_level + 1)}"
                if current_ref
                else None
            )
            valid = declared_target.question_ref == expected_substep_ref
        if not valid:
            return state
        target = ResponseTarget(
            declared_target.question_ref, declared_target.target_type
        )
        return StateReducer.set_pending(state, target)
