from __future__ import annotations

import json
import logging
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.board.validation import validate_board
from app.core.config import settings
from app.lesson.context import LessonContext
from app.llm import prompts
from app.llm.provider import LLMError, LLMProvider
from app.models.assessment import AssessmentQuestion
from app.models.board_explanation import BoardExplanation
from app.models.message import Message
from app.models.session import LessonSession
from app.models.student import Student
from app.repositories.assessment_repo import AssessmentRepository
from app.repositories.board_repo import BoardExplanationRepository
from app.repositories.message_repo import MessageRepository
from app.repositories.session_repo import SessionRepository
from app.schemas.board import BoardListResponse, BoardResponse, BoardSpec, BoardSummary

log = logging.getLogger("app.services.board_service")

# One repair attempt. A second rejection means the model is not going to produce
# a usable board here, and the student is better served by a clear error than by
# a third wait.
_MAX_ATTEMPTS = 2

# A board is a handful of short lines; a couple of workers keeps the first block
# speaking quickly without opening a connection per block.
_NARRATION_WORKERS = 3
# Transport slice for audio_delta, in base64 characters.
_AUDIO_DELTA_CHARS = 32 * 1024


def _ndjson(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False) + "\n"


class BoardService:
    """Generates and serves visual board explanations.

    Owns its transaction, like every other service here. It resolves sessions
    through SessionRepository rather than through TutorService: services are
    siblings sharing repositories, not layers.
    """

    def __init__(self, db: Session, llm: LLMProvider, student: Student):
        self.db = db
        self.llm = llm
        self.student = student
        self.sessions = SessionRepository(db)
        self.questions = AssessmentRepository(db)
        self.messages = MessageRepository(db)
        self.boards = BoardExplanationRepository(db)

    # ---- helpers ----

    def _get_session(self, session_id: int) -> LessonSession:
        session = self.sessions.get_specific_session(session_id, self.student.id)
        if session is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
        return session

    @staticmethod
    def _require_enabled() -> None:
        if not settings.BOARD_EXPLANATION_ENABLED:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, "Board explanations are not enabled"
            )

    @staticmethod
    def _to_response(board: BoardExplanation) -> BoardResponse:
        return BoardResponse(
            id=board.id,
            kind=board.kind,
            message_id=board.message_id,
            question_id=board.question_id,
            spec=BoardSpec.model_validate(board.content_json),
            created_at=board.created_at,
        )

    # ---- read ----

    def list_boards(self, session_id: int) -> BoardListResponse:
        """Capability discovery plus every board in this session.

        Deliberately answers 200 even when the flag is off: the frontend has no
        feature-flag system, so this is how it learns not to render the action.
        Ownership is still enforced.
        """
        self._get_session(session_id)
        if not settings.BOARD_EXPLANATION_ENABLED:
            return BoardListResponse(enabled=False, boards=[])
        return BoardListResponse(
            enabled=True,
            boards=[
                BoardSummary(
                    id=board.id,
                    kind=board.kind,
                    message_id=board.message_id,
                    question_id=board.question_id,
                    title=board.title,
                    created_at=board.created_at,
                )
                for board in self.boards.list_for_session(session_id)
            ],
        )

    def get_board(self, session_id: int, board_id: int) -> BoardResponse:
        self._require_enabled()
        self._get_session(session_id)
        board = self.boards.get_owned(board_id, session_id)
        if board is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Board explanation not found")
        return self._to_response(board)

    def get_narration(self, session_id: int, board_id: int) -> list[str]:
        """The spoken line for each block, in order — what the tutor says while
        that block is being written."""
        board = self.get_board(session_id, board_id)
        return [block.narration for block in board.spec.blocks]

    def stream_narration(self, session_id: int, board_id: int, voice) -> Iterator[str]:
        """Speak the board, one block at a time, as NDJSON audio events.

        Emits the same audio_start / audio_delta / audio_end shape as the chat
        speech stream, keyed by block index, so the frontend's existing ordered
        playback queue works unchanged. The player reveals block N when chunk N
        starts, which is what makes the writing land with the words.

        Synthesis runs on a small pool but is emitted strictly in order: block 2
        must not be heard before block 1 even if it finishes first. A block whose
        audio fails is skipped rather than aborting the rest — a silent step is
        better than a board that stops halfway.
        """
        board = self.get_board(session_id, board_id)
        narrations = [block.narration for block in board.spec.blocks]

        def generate() -> Iterator[str]:
            started = time.perf_counter()
            with ThreadPoolExecutor(max_workers=_NARRATION_WORKERS) as pool:
                futures = [pool.submit(voice.synthesize_speech, text) for text in narrations]
                for index, future in enumerate(futures):
                    try:
                        audio_b64 = future.result()
                    except Exception:  # noqa: BLE001 - one silent block, not a dead board
                        log.warning(
                            "board narration chunk failed session_id=%s board_id=%s block=%d",
                            session_id,
                            board_id,
                            index,
                        )
                        continue
                    yield _ndjson({"type": "audio_start", "chunk_id": index})
                    for offset in range(0, len(audio_b64), _AUDIO_DELTA_CHARS):
                        yield _ndjson(
                            {
                                "type": "audio_delta",
                                "chunk_id": index,
                                "data": audio_b64[offset : offset + _AUDIO_DELTA_CHARS],
                            }
                        )
                    yield _ndjson({"type": "audio_end", "chunk_id": index})
            log.info(
                "board narration done session_id=%s board_id=%s blocks=%d duration_ms=%.1f",
                session_id,
                board_id,
                len(narrations),
                (time.perf_counter() - started) * 1000,
            )
            yield _ndjson({"type": "done"})

        return generate()

    # ---- generate: lesson ----

    def open_lesson_on_board(self, session_id: int, focus: str | None = None) -> tuple[BoardResponse, bool]:
        """Teach on the board, anchored to a tutor turn in the transcript.

        Serves both the lesson opening and a mid-lesson request; the only
        difference is how much conversation there is to react to, which the
        prompt reads from history. Anchoring to a message is what makes the board
        replayable from the chat later.
        """
        self._require_enabled()
        session = self._get_session(session_id)

        # The lesson opening is generated once. A later request is a fresh board,
        # so only the intro is deduplicated.
        if focus is None:
            existing = next(
                (b for b in self.boards.list_for_session(session.id) if b.kind == "lesson_intro"),
                None,
            )
            if existing is not None:
                log.info(
                    "board reused session_id=%s kind=lesson_intro board_id=%s",
                    session_id,
                    existing.id,
                )
                return self._to_response(existing), False

        ctx = LessonContext(self.db, session, self.student, self.llm)
        tutor_ctx = ctx.build_tutor_context(focus)
        spec, duration_ms = self._generate(
            lambda retry: prompts.board_lesson_prompt(
                tutor_ctx,
                max_blocks=settings.BOARD_MAX_BLOCKS,
                focus=focus,
                retry_reason=retry,
            ),
            question_text=focus or session.subtopic or session.topic,
            correct_answer=None,
            session_id=session_id,
            label="lesson_intro" if focus is None else "chat",
        )

        # The board's own opening line becomes the tutor's chat message, so the
        # transcript reads naturally and the board has something to hang off.
        message = Message(session_id=session.id, role="tutor", content=spec.intro)
        self.db.add(message)
        self.db.flush()

        return self._persist(
            session_id=session.id,
            kind="lesson_intro" if focus is None else "chat",
            spec=spec,
            duration_ms=duration_ms,
            message_id=message.id,
        )

    # ---- generate: practice review ----

    def review_question_on_board(self, session_id: int, question_id: int) -> tuple[BoardResponse, bool]:
        """Explain a question the student has already been graded on.

        Refuses while the question is unanswered: during practice the student
        works it out alone, and a board then would be doing the work for them.
        """
        self._require_enabled()
        session = self._get_session(session_id)
        question = self.questions.get(question_id)
        if question is None or question.session_id != session.id:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, "Question not found in this session"
            )
        if question.is_correct is None:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "This question hasn't been checked yet — have a go at it first.",
            )

        existing = self.boards.get_for_question(question.id)
        if existing is not None:
            log.info(
                "board reused session_id=%s question_id=%s board_id=%s",
                session_id,
                question_id,
                existing.id,
            )
            return self._to_response(existing), False

        spec, duration_ms = self._generate(
            lambda retry: prompts.board_review_prompt(
                question_text=question.question_text,
                correct_answer=question.correct_answer,
                solution_steps=question.solution_steps,
                student_answer=question.student_answer,
                feedback=question.feedback,
                max_blocks=settings.BOARD_MAX_BLOCKS,
                retry_reason=retry,
            ),
            question_text=question.question_text,
            correct_answer=question.correct_answer,
            session_id=session_id,
            label="practice_review",
        )
        return self._persist(
            session_id=session.id,
            kind="practice_review",
            spec=spec,
            duration_ms=duration_ms,
            question_id=question.id,
        )

    # ---- shared generation / persistence ----

    def _persist(
        self,
        *,
        session_id: int,
        kind: str,
        spec: BoardSpec,
        duration_ms: float,
        message_id: int | None = None,
        question_id: int | None = None,
    ) -> tuple[BoardResponse, bool]:
        board = BoardExplanation(
            session_id=session_id,
            kind=kind,
            message_id=message_id,
            question_id=question_id,
            title=spec.title[:120],
            content_json=spec.model_dump(mode="json"),
            model=settings.OPENAI_BOARD_MODEL,
            duration_ms=duration_ms,
        )
        try:
            self.boards.add(board)
            self.db.commit()
        except IntegrityError:
            # A concurrent request won the unique anchor. Both calls paid for a
            # generation, but only one board can exist — return the winner's.
            self.db.rollback()
            winner = (
                self.boards.get_for_question(question_id)
                if question_id is not None
                else self.boards.get_for_message(message_id)
                if message_id is not None
                else None
            )
            if winner is None:
                raise
            return self._to_response(winner), False
        return self._to_response(board), True

    def _generate(
        self,
        build_prompt,
        *,
        question_text: str,
        correct_answer: str | None,
        session_id: int,
        label: str,
    ) -> tuple[BoardSpec, float]:
        """Ask the model for a board, retrying once with the rejection reason.

        No transaction is open and no row is locked while the model is called:
        grading writes to the same rows a review board reads, and a student who
        asked for a board must never block their own submit.
        """
        started = time.perf_counter()
        log.info("board generate start session_id=%s kind=%s", session_id, label)
        retry_reason: str | None = None
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            system, user = build_prompt(retry_reason)
            try:
                raw = self.llm.generate_board_explanation(system, user)
            except LLMError as exc:
                log.error(
                    "board generate failed session_id=%s kind=%s error=%s",
                    session_id,
                    label,
                    type(exc).__name__,
                )
                raise HTTPException(
                    status.HTTP_502_BAD_GATEWAY, f"Board service unavailable: {exc}"
                ) from exc

            result = validate_board(
                raw,
                question_text=question_text,
                correct_answer=correct_answer,
                max_blocks=settings.BOARD_MAX_BLOCKS,
            )
            if result.ok and result.spec is not None:
                duration_ms = (time.perf_counter() - started) * 1000
                log.info(
                    "board generate done session_id=%s kind=%s duration_ms=%.1f "
                    "blocks=%d dropped=%d attempt=%d model=%s",
                    session_id,
                    label,
                    duration_ms,
                    len(result.spec.blocks),
                    len(result.dropped),
                    attempt,
                    settings.OPENAI_BOARD_MODEL,
                )
                return result.spec, duration_ms

            retry_reason = result.rejection
            log.warning(
                "board generate rejected session_id=%s kind=%s reason=%s attempt=%d",
                session_id,
                label,
                retry_reason,
                attempt,
            )

        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "The tutor couldn't draw this one. Please try again.",
        )
