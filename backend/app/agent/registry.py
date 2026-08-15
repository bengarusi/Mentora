from __future__ import annotations

import json
import time
import concurrent.futures
from dataclasses import asdict, dataclass
from typing import Any, Callable

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.orm import Session

from app.agent.evaluation import AnswerEvaluator
from app.agent.schemas import Annotation, EvaluationResult, HomeworkExercise, SessionState
from app.core.config import settings
from app.files.retrieval import get_material_retriever
from app.files.storage import get_file_storage
from app.llm.provider import LLMProvider
from app.llm.tooling import ToolCall, ToolSchema
from app.models.session import LessonSession
from app.models.student import Student
from app.services.material_service import MaterialService


class _ToolArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EvaluateAnswerArgs(_ToolArgs):
    student_answer: str = Field(min_length=1, max_length=2000)
    question_ref: str = Field(min_length=1, max_length=200)


class AnalyzeHomeworkArgs(_ToolArgs):
    pass


class RecordLearningAnnotationArgs(_ToolArgs):
    kind: str = Field(pattern="^(misconception|note)$")
    text: str = Field(min_length=1, max_length=500)
    skill: str | None = Field(default=None, max_length=120)


class SearchStudyMaterialsArgs(_ToolArgs):
    query: str = Field(min_length=1, max_length=500)
    limit: int = Field(default=3, ge=1, le=5)


class GetStudentProgressArgs(_ToolArgs):
    topic: str | None = Field(default=None, max_length=120)


class GeneratePracticeQuestionArgs(_ToolArgs):
    skill: str = Field(min_length=1, max_length=120)
    difficulty: int = Field(ge=1, le=3)


@dataclass(frozen=True)
class ToolOutput:
    content: dict[str, Any]
    evaluation: EvaluationResult | None = None
    annotation: Annotation | None = None
    duration_ms: float = 0.0
    error: str | None = None


@dataclass(frozen=True)
class _Definition:
    schema: ToolSchema
    model: type[BaseModel]
    handler: Callable[[BaseModel], ToolOutput]


def outline_from_json(value: list[dict] | None) -> list[HomeworkExercise]:
    return [HomeworkExercise(**item) for item in (value or [])]


class ToolRegistry:
    """Validated, server-bound tool adapters. Handlers return observations only."""

    def __init__(
        self,
        db: Session,
        llm: LLMProvider,
        student: Student,
        session: LessonSession,
    ):
        self.db = db
        self.llm = llm
        self.student = student
        self.session = session
        self._current_exercise_index = 1
        self._definitions = {
            "evaluateAnswer": self._definition(
                "evaluateAnswer",
                "Evaluate a student answer against a server-held homework question.",
                EvaluateAnswerArgs,
                self._evaluate,
            ),
            "analyzeHomework": self._definition(
                "analyzeHomework",
                "Read the server-held homework outline and current exercise position.",
                AnalyzeHomeworkArgs,
                self._analyze,
            ),
            "recordLearningAnnotation": self._definition(
                "recordLearningAnnotation",
                "Record an advisory misconception or note. Cannot change mastery or solved state.",
                RecordLearningAnnotationArgs,
                self._annotate,
            ),
            "searchStudyMaterials": self._definition(
                "searchStudyMaterials",
                "Search this student's study materials for relevant passages.",
                SearchStudyMaterialsArgs,
                self._search,
            ),
            # Registered extension points, intentionally not present in
            # TeacherAgent.exposed_tools for the homework MVP.
            "getStudentProgress": self._definition(
                "getStudentProgress",
                "Read deterministic skill evidence for this student.",
                GetStudentProgressArgs,
                self._progress,
            ),
            "generatePracticeQuestion": self._definition(
                "generatePracticeQuestion",
                "Generate one practice candidate without changing lesson state.",
                GeneratePracticeQuestionArgs,
                self._generate_practice,
            ),
        }

    def bind_state(self, state: SessionState) -> None:
        """Refresh the read-only state snapshot exposed by observation tools."""
        self._current_exercise_index = state.current_exercise_index

    @staticmethod
    def _definition(name, description, model, handler) -> _Definition:
        return _Definition(
            ToolSchema(name, description, model.model_json_schema()), model, handler
        )

    def schemas(self, names: tuple[str, ...] | None = None) -> list[ToolSchema]:
        selected = names or tuple(self._definitions)
        return [self._definitions[name].schema for name in selected]

    def invoke(self, call: ToolCall) -> ToolOutput:
        started = time.perf_counter()
        definition = self._definitions.get(call.name)
        if definition is None:
            return ToolOutput(
                {"ok": False, "error": "unknown_tool"}, error="unknown_tool"
            )
        try:
            args = definition.model.model_validate(call.arguments)
        except ValidationError as exc:
            return ToolOutput(
                {"ok": False, "error": "invalid_arguments", "details": exc.errors(include_url=False)},
                duration_ms=(time.perf_counter() - started) * 1000,
                error="invalid_arguments",
            )

        # Tool handlers only produce observations; authoritative mutations
        # happen later in AgentRunner. That makes it safe to abandon a timed
        # out handler and ignore any eventual result without changing state.
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        future = executor.submit(definition.handler, args)
        try:
            result = future.result(timeout=settings.AGENT_TOOL_TIMEOUT_S)
            duration_ms = (time.perf_counter() - started) * 1000
            return ToolOutput(
                result.content,
                result.evaluation,
                result.annotation,
                duration_ms,
                result.error,
            )
        except concurrent.futures.TimeoutError:
            future.cancel()
            return ToolOutput(
                {"ok": False, "error": "tool_timeout"},
                duration_ms=(time.perf_counter() - started) * 1000,
                error="tool_timeout",
            )
        except Exception as exc:  # noqa: BLE001 - tools degrade into observations
            return ToolOutput(
                {"ok": False, "error": "tool_failed"},
                duration_ms=(time.perf_counter() - started) * 1000,
                error=type(exc).__name__,
            )
        finally:
            # Do not wait for a blocked network/tool call after its budget.
            executor.shutdown(wait=False, cancel_futures=True)

    def _evaluate(self, raw: BaseModel) -> ToolOutput:
        args = EvaluateAnswerArgs.model_validate(raw)
        result = AnswerEvaluator(self.llm).evaluate(
            args.student_answer,
            args.question_ref,
            outline_from_json(self.session.homework_outline),
        )
        return ToolOutput(result.as_observation(), evaluation=result)

    def _analyze(self, raw: BaseModel) -> ToolOutput:
        outline = outline_from_json(self.session.homework_outline)
        return ToolOutput(
            {
                "ok": True,
                "total": len(outline),
                "current_exercise_index": self._current_exercise_index,
                "exercises": [
                    {"ref": item.ref, "text": item.text, "target_type": item.target_type}
                    for item in outline
                ],
            }
        )

    def _annotate(self, raw: BaseModel) -> ToolOutput:
        args = RecordLearningAnnotationArgs.model_validate(raw)
        annotation = Annotation(args.kind, args.text, args.skill)
        return ToolOutput({"ok": True, "annotation": asdict(annotation)}, annotation=annotation)

    def _search(self, raw: BaseModel) -> ToolOutput:
        args = SearchStudyMaterialsArgs.model_validate(raw)
        chunks = MaterialService(
            self.db,
            self.student,
            get_file_storage(),
            get_material_retriever(),
        ).retrieve_relevant(
            query=args.query,
            subject=self.session.subject,
            topic=None,
            limit=args.limit,
        )
        return ToolOutput(
            {
                "ok": True,
                "results": [
                    {"title": item.material_title, "content": item.content}
                    for item in chunks
                ],
            }
        )

    def _progress(self, raw: BaseModel) -> ToolOutput:
        from app.models.student_mastery import StudentSkillMastery

        args = GetStudentProgressArgs.model_validate(raw)
        query = self.db.query(StudentSkillMastery).filter(
            StudentSkillMastery.student_id == self.student.id
        )
        if args.topic:
            query = query.filter(StudentSkillMastery.topic == args.topic)
        rows = query.order_by(StudentSkillMastery.topic, StudentSkillMastery.skill).all()
        return ToolOutput(
            {
                "ok": True,
                "skills": [
                    {
                        "topic": row.topic,
                        "skill": row.skill,
                        "mastery_estimate": row.mastery_estimate,
                        "attempts": row.attempts,
                        "correct": row.correct,
                    }
                    for row in rows
                ],
            }
        )

    def _generate_practice(self, raw: BaseModel) -> ToolOutput:
        from app.lesson.context import LessonContext
        from app.lesson.state import _validate_generated_answer

        args = GeneratePracticeQuestionArgs.model_validate(raw)
        ctx = LessonContext(self.db, self.session, self.student, self.llm)
        candidates = self.llm.generate_practice_questions(
            ctx.build_tutor_context(), set_number=1
        )
        candidate = next(
            (item for item in candidates if item.difficulty == args.difficulty),
            candidates[0] if candidates else None,
        )
        if candidate is None:
            return ToolOutput(
                {"ok": False, "error": "no_practice_question"},
                error="no_practice_question",
            )
        answer = _validate_generated_answer(candidate.question, candidate.correct_answer)
        return ToolOutput(
            {
                "ok": True,
                "skill": args.skill,
                "difficulty": candidate.difficulty,
                "question": candidate.question,
                "correct_answer": answer,
                "solution_steps": candidate.solution_steps,
                "explanation": candidate.explanation,
            }
        )


def canonical_call_key(call: ToolCall) -> tuple[str, str]:
    return call.name, json.dumps(call.arguments, sort_keys=True, ensure_ascii=False)
