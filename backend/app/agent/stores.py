from __future__ import annotations

from dataclasses import asdict

from sqlalchemy.orm import Session
from sqlalchemy.sql import func

from app.agent.schemas import (
    Annotation,
    MasteryDelta,
    ResponseTarget,
    SessionState,
)
from app.models.agent_session_state import AgentSessionState
from app.models.agent_trace import AgentTrace
from app.models.student_mastery import StudentSkillMastery


class SessionStateStore:
    """The only persistence mechanism for per-homework-session agent state."""

    def __init__(self, db: Session):
        self.db = db

    def load(self, session_id: int, *, for_update: bool = False) -> SessionState:
        query = self.db.query(AgentSessionState).filter(
            AgentSessionState.session_id == session_id
        )
        if for_update:
            query = query.with_for_update()
        row = query.one_or_none()
        if row is None:
            return SessionState(session_id=session_id)
        target = ResponseTarget(**row.response_target) if row.response_target else None
        return SessionState(
            session_id=row.session_id,
            current_goal=row.current_goal or "",
            current_exercise_index=row.current_exercise_index,
            awaiting_response=row.awaiting_response,
            response_target=target,
            hint_level=row.hint_level,
            solved_refs=frozenset(row.solved_refs or []),
            annotations=tuple(Annotation(**item) for item in (row.annotations or [])),
            materials_used=tuple(row.materials_used or []),
            recent_evaluations=tuple(row.recent_evaluations or []),
            recommended_next_action=row.recommended_next_action or "",
            applied_evaluation_keys=frozenset(row.applied_evaluation_keys or []),
        )

    def save(self, state: SessionState) -> None:
        row = (
            self.db.query(AgentSessionState)
            .filter(AgentSessionState.session_id == state.session_id)
            .one_or_none()
        )
        if row is None:
            row = AgentSessionState(session_id=state.session_id)
            self.db.add(row)
        row.current_goal = state.current_goal
        row.current_exercise_index = state.current_exercise_index
        row.awaiting_response = state.awaiting_response
        row.response_target = asdict(state.response_target) if state.response_target else None
        row.hint_level = state.hint_level
        row.solved_refs = sorted(state.solved_refs)
        row.annotations = [asdict(item) for item in state.annotations]
        row.materials_used = list(state.materials_used)
        row.recent_evaluations = list(state.recent_evaluations)
        row.recommended_next_action = state.recommended_next_action
        row.applied_evaluation_keys = sorted(state.applied_evaluation_keys)
        self.db.flush()


class StudentProgressStore:
    """The only persistence mechanism for deterministic long-term evidence."""

    def __init__(self, db: Session):
        self.db = db

    def apply(
        self,
        *,
        student_id: int,
        subject: str,
        topic: str,
        delta: MasteryDelta,
    ) -> None:
        skill = delta.skill or topic
        row = (
            self.db.query(StudentSkillMastery)
            .filter(
                StudentSkillMastery.student_id == student_id,
                StudentSkillMastery.subject == subject,
                StudentSkillMastery.topic == topic,
                StudentSkillMastery.skill == skill,
            )
            .one_or_none()
        )
        if row is None:
            row = StudentSkillMastery(
                student_id=student_id,
                subject=subject,
                topic=topic,
                skill=skill,
                open_misconceptions=[],
            )
            self.db.add(row)
        row.attempts = (row.attempts or 0) + 1
        row.correct = (row.correct or 0) + int(delta.correct)
        row.mastery_estimate = row.correct / row.attempts
        row.last_evidence_at = func.now()
        self.db.flush()


class AgentTraceStore:
    def __init__(self, db: Session):
        self.db = db

    def add(
        self,
        *,
        run_id: str,
        session_id: int,
        step: int,
        kind: str,
        tool_name: str | None = None,
        args_json: dict | None = None,
        result_json: dict | None = None,
        duration_ms: float | None = None,
        error: str | None = None,
    ) -> None:
        self.db.add(
            AgentTrace(
                run_id=run_id,
                session_id=session_id,
                step=step,
                kind=kind,
                tool_name=tool_name,
                args_json=args_json,
                result_json=result_json,
                duration_ms=duration_ms,
                error=error,
            )
        )
        self.db.flush()
