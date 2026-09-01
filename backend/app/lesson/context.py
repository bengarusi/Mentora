import logging

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.enums import LessonPhase, MaterialStatus, MessageRole, SessionMode, Subject
from app.files.retrieval import MaterialRetriever, get_material_retriever
from app.llm.provider import LLMProvider, MaterialExcerpt, TutorContext
from app.models.material import StudyMaterial
from app.models.message import Message
from app.models.session import LessonSession
from app.models.student import Student
from app.repositories.assessment_repo import AssessmentRepository
from app.repositories.material_repo import MaterialRepository
from app.repositories.message_repo import MessageRepository
from app.repositories.performance_repo import PerformanceRepository

log = logging.getLogger("app.lesson.context")

_HISTORY_LIMIT = 10
#: Passages pulled per turn. Small on purpose — the lesson leads, the material
#: supports it.
_MATERIAL_TOP_K = 3


class LessonContext:
    """Context object of the State pattern. Built fresh per request; the only
    cross-request state is the session.phase column (single source of truth).
    The current LessonState is rehydrated from that column."""

    def __init__(
        self,
        db: Session,
        session: LessonSession,
        student: Student,
        llm: LLMProvider,
        retriever: MaterialRetriever | None = None,
        turn_id: str | None = None,
    ):
        self.db = db
        self.session = session
        self.student = student
        self.llm = llm
        self.retriever = retriever or get_material_retriever()
        self.turn_id = turn_id
        self.messages = MessageRepository(db)
        self.questions = AssessmentRepository(db)
        self.performances = PerformanceRepository(db)
        self.materials = MaterialRepository(db)

        from app.lesson.state import state_for_phase

        self.state = state_for_phase(LessonPhase(session.phase))

    def move_to_next_phase_of_the_conversation(self, phase: LessonPhase) -> None:
        from app.lesson.state import state_for_phase

        previous_phase = self.session.phase
        self.session.phase = phase.value
        self.state = state_for_phase(phase)
        log.info(
            "phase transition session_id=%s from=%s to=%s",
            self.session.id,
            previous_phase,
            phase.value,
        )

    def save_tutor_message_to_db(self, content: str) -> Message:
        return self.messages.add(
            Message(
                session_id=self.session.id,
                role=MessageRole.TUTOR.value,
                content=content,
            )
        )

    def save_student_message_to_db(self, content: str) -> Message:
        return self.messages.add(
            Message(
                session_id=self.session.id,
                role=MessageRole.STUDENT.value,
                content=content,
            )
        )

    def build_tutor_context(self, retrieval_query: str | None = None) -> TutorContext:
        """Assemble the LLM's view of this turn.

        *retrieval_query* is normally the student's latest message. When given,
        the student's own study materials are searched and only the passages
        that match are attached — uploads are never injected wholesale."""
        if self.session.subject == Subject.MATH.value:
            level = self.student.math_level
        else:
            level = self.student.english_level

        history = self.messages.get_recent_session_messages(
            self.session.id, _HISTORY_LIMIT
        )
        recent = [(m.role, m.content) for m in history]

        return TutorContext(
            subject=self.session.subject,
            topic=self.session.topic,
            goal_text=self.session.goal_text,
            grade=self.student.grade,
            age=self.student.age,
            level=level,
            recent_messages=recent,
            subtopic=getattr(self.session, "subtopic", None),
            difficulty=getattr(self.session, "difficulty", None),
            mode=getattr(self.session, "mode", SessionMode.LESSON.value),
            material_excerpts=self._retrieve_excerpts(retrieval_query),
            homework_text=self._homework_text(),
            board_digests=self._board_digests(),
        )

    def _board_digests(self) -> list[str]:
        """Recall the boards recently shown in this session.

        Imported lazily and guarded: a board that can no longer be parsed must
        degrade to "the tutor forgot that one", never break the chat turn."""
        if not settings.BOARD_EXPLANATION_ENABLED:
            return []
        from app.board.digest import digest_for
        from app.repositories.board_repo import BoardExplanationRepository
        from app.schemas.board import BoardSpec

        rows = BoardExplanationRepository(self.db).list_for_session(self.session.id)
        digests = []
        for row in rows[-settings.BOARD_DIGEST_LIMIT :]:
            try:
                spec = BoardSpec.model_validate(row.content_json)
            except Exception:  # noqa: BLE001 - a stale board is not a broken chat
                continue
            digests.append(
                digest_for(spec, char_budget=settings.BOARD_DIGEST_CHAR_BUDGET)
            )
        return digests

    def _retrieve_excerpts(self, query: str | None) -> list[MaterialExcerpt]:
        """Relevant passages from the student's study materials, or nothing.

        Homework sessions skip this: their own attached file is the material,
        and mixing in the wider library would only dilute the context."""
        if not query or self.session.mode == SessionMode.HOMEWORK.value:
            return []
        try:
            chunks = self.retriever.retrieve(
                self.db,
                student_id=self.student.id,
                query=query,
                subject=self.session.subject,
                topic=self.session.topic,
                limit=_MATERIAL_TOP_K,
            )
        except Exception:  # noqa: BLE001 - retrieval is an enhancement, never a blocker
            log.warning(
                "material retrieval failed session_id=%s", self.session.id, exc_info=True
            )
            return []

        # Trim to a hard character budget so a long document can't dominate the
        # prompt (or its cost), keeping the highest-scoring passages.
        budget = settings.MATERIAL_CONTEXT_CHAR_BUDGET
        excerpts: list[MaterialExcerpt] = []
        for chunk in chunks:
            if budget <= 0:
                break
            content = chunk.content[:budget]
            budget -= len(content)
            excerpts.append(
                MaterialExcerpt(title=chunk.material_title, content=content)
            )
        if excerpts:
            log.info(
                "material context injected session_id=%s query=%r chunks=%s",
                self.session.id,
                query,
                [
                    {
                        "material_id": c.material_id,
                        "title": c.material_title,
                        "chunk_index": c.chunk_index,
                        "score": round(c.score, 3),
                    }
                    for c in chunks[: len(excerpts)]
                ],
            )
        else:
            log.info(
                "material context none session_id=%s query=%r "
                "(no chunk passed the relevance thresholds)",
                self.session.id,
                query,
            )
        return excerpts

    def _ready_homework_materials(self) -> list[StudyMaterial]:
        if self.session.mode != SessionMode.HOMEWORK.value:
            return []
        return [
            material
            for material in self.materials.list_session_materials(self.session.id)
            if material.status == MaterialStatus.READY.value and material.extracted_text
        ]

    def homework_source_documents(self) -> list[str]:
        """Complete extracted bodies, retaining upload/page boundaries."""
        return [material.extracted_text for material in self._ready_homework_materials()]

    def _homework_text(self) -> str | None:
        """Prompt-safe view of the homework, bounded to leave room for chat.

        This budget is a presentation limit only. Question segmentation and
        state read :meth:`homework_source_documents` instead — applying this
        cap there used to erase every question after the first 4,000
        characters.
        """
        rows = self._ready_homework_materials()
        if not rows:
            return None
        source = "\n\n".join(
            f"--- {material.title or material.filename} ---\n{material.extracted_text}"
            for material in rows
        )
        return source[: settings.MATERIAL_CONTEXT_CHAR_BUDGET]
