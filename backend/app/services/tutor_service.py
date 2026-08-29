import base64
import concurrent.futures
import json
import logging
import threading
import time

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from collections.abc import Iterator

from app.core.enums import (
    DifficultyLevel,
    LessonPhase,
    SessionMode,
    SessionStatus,
    SuccessLevel,
)
from app.core.config import settings
from app.files.homework import count_exercises, segment_exercises
from app.lesson.context import LessonContext
from app.lesson.state import (
    HomeworkHelpState,
    InvalidLessonAction,
    PracticeState,
    TeachingState,
    _ConversationalState,
    _annotate_math,
    _homework_agent_should_run,
    verify_chat_answer,
)
from app.llm.provider import LLMError, LLMProvider
from app.models.performance import Performance
from app.models.agent_session_state import AgentSessionState
from app.models.agent_trace import AgentTrace
from app.models.board_explanation import BoardExplanation
from app.models.session import LessonSession
from app.models.student import Student
from app.repositories.material_repo import MaterialRepository
from app.repositories.session_repo import SessionRepository
from app.schemas.practice import (
    GradedPracticeItem,
    PracticeAnswersSubmit,
    PracticeStartResult,
    PracticeSubmitResult,
    PracticeSummaryDTO,
    PracticeSetResult,
    PracticeQuestionDTO,
)
from app.schemas.material import HomeworkSessionCreate
from app.schemas.session import SessionCreate
from app.schemas.tutor import HomeworkProgress, PhaseResult, TurnResult
from app.services.speech_chunker import SpeechChunker
from app.services.voice_service import VoiceService, VoiceServiceError

log = logging.getLogger("app.services.tutor_service")

# Max TTS jobs running at once during a speech-stream turn. Set to 1 for a fully
# sequential fallback (same code path). Audio is always emitted in chunk order,
# and text streaming is never blocked waiting on a TTS job.
MAX_CONCURRENT_TTS = 2
# Transport slice size for audio_delta events (the frontend reassembles per chunk_id).
_AUDIO_DELTA_BYTES = 32 * 1024

# Homework sessions reuse LessonSession's mandatory curriculum columns, which
# don't apply to a file the student brought in. These stand in so the row stays
# valid and the UI has something meaningful to label the session with.
HOMEWORK_TOPIC = "Homework Help"
HOMEWORK_SUBTOPIC = "My homework"
HOMEWORK_GOAL = "I want help understanding and solving my homework."


class TutorService:
    """Orchestrates the lesson flow: loads + authorizes the session, drives the
    State machine, persists via repositories, and owns the transaction."""

    def __init__(self, db: Session, llm: LLMProvider, student: Student):
        self.db = db
        self.llm = llm
        self.student = student
        self.sessions = SessionRepository(db)

    # ---- helpers ----

    def _build_ctx(
        self, session: LessonSession, *, turn_id: str | None = None
    ) -> LessonContext:
        return LessonContext(
            self.db, session, self.student, self.llm, turn_id=turn_id
        )

    def _get_session(self, session_id: int) -> LessonSession:
        session = self.sessions.get_specific_session(session_id, self.student.id)
        if session is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Session not found"
            )
        return session

    def _require_phase(self, session: LessonSession, phase: LessonPhase) -> None:
        if session.phase != phase.value:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"This action requires phase '{phase.value}', current phase is '{session.phase}'.",
            )

    def _require_practice_phase(self, session: LessonSession) -> None:
        self._require_phase(session, LessonPhase.PRACTICE)

    @staticmethod
    def _llm_error(exc: LLMError) -> HTTPException:
        return HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Tutor service unavailable: {exc}",
        )

    @staticmethod
    def _require_agent_turn_id(use_agent: bool, turn_id: str | None) -> None:
        if use_agent and not turn_id:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "turn_id is required for an agentic homework turn.",
            )

    # ---- session creation ----

    def create_lesson_and_generate_first_explanation(
        self, data: SessionCreate
    ) -> LessonSession:
        subtopic = (data.subtopic or "").strip()
        if not subtopic:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "A subtopic is required to start a lesson.",
            )
        session = self.sessions.add(
            LessonSession(
                student_id=self.student.id,
                subject=data.subject.value,
                topic=data.topic,
                subtopic=subtopic,
                goal_text=data.goal_text,
                status=SessionStatus.ACTIVE.value,
                phase=LessonPhase.TEACHING.value,
            )
        )
        ctx = self._build_ctx(session)
        try:
            ctx.state.generate_phase_opening_message(ctx)
        except LLMError as exc:
            raise self._llm_error(exc)
        self.db.commit()
        self.db.refresh(session)
        log.info(
            "lesson created session_id=%s student_id=%s subject=%s topic=%s phase=%s",
            session.id,
            self.student.id,
            session.subject,
            session.topic,
            session.phase,
        )
        return session

    # ---- homework help session ----

    def create_homework_session(self, data: HomeworkSessionCreate) -> LessonSession:
        """Open an empty Homework Help session.

        No opening message yet: the tutor has nothing useful to say until the
        student's homework has been uploaded and read. The frontend uploads
        into this session, then calls `analyze_homework`."""
        session = self.sessions.add(
            LessonSession(
                student_id=self.student.id,
                subject=data.subject,
                topic=HOMEWORK_TOPIC,
                subtopic=(data.title or "").strip() or HOMEWORK_SUBTOPIC,
                goal_text=HOMEWORK_GOAL,
                status=SessionStatus.ACTIVE.value,
                mode=SessionMode.HOMEWORK.value,
                phase=LessonPhase.HOMEWORK_HELP.value,
            )
        )
        self.db.commit()
        self.db.refresh(session)
        log.info(
            "homework session created session_id=%s student_id=%s",
            session.id,
            self.student.id,
        )
        return session

    def list_homework_sessions(self) -> list[LessonSession]:
        """The student's Homework Help sessions with real activity in them,
        newest first, so they can resume one instead of starting a fresh
        session every visit. Sessions where "Start Homework Help" was clicked
        but nothing was ever said are not real conversations and are excluded
        — see get_homework_sessions_with_activity."""
        return self.sessions.get_homework_sessions_with_activity(self.student.id)

    def rename_homework_session(self, session_id: int, title: str) -> LessonSession:
        """Let the student give a Homework Help session a name of their own,
        replacing the default "My homework" shown on the Files page."""
        title = title.strip()
        if not title:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "Title cannot be empty."
            )
        session = self._get_session(session_id)
        if session.mode != SessionMode.HOMEWORK.value:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Only Homework Help sessions can be renamed.",
            )
        session.subtopic = title
        self.db.commit()
        self.db.refresh(session)
        return session

    def delete_homework_session(self, session_id: int) -> list[str]:
        """Delete a Homework Help session and everything hanging off it.

        Returns the storage keys of the files it held, for the caller to unlink
        once this has committed — the same ordering MaterialService uses, so a
        storage failure can never leave a row pointing at deleted bytes.

        Three tables reference a session without an ORM cascade (boards, agent
        traces and agent state), so they are cleared here explicitly. Boards go
        first: they also reference messages and questions, which the session's
        own cascade is about to remove.
        """
        session = self._get_session(session_id)
        if session.mode != SessionMode.HOMEWORK.value:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Only Homework Help sessions can be deleted here.",
            )

        keys = [
            material.storage_key
            for material in MaterialRepository(self.db).list_session_materials(session.id)
            if material.storage_key
        ]

        for model in (BoardExplanation, AgentTrace, AgentSessionState):
            self.db.query(model).filter(model.session_id == session.id).delete(
                synchronize_session=False
            )
        self.db.delete(session)  # messages, questions, performance, materials cascade
        self.db.commit()
        log.info(
            "homework session deleted session_id=%s student_id=%s files=%d",
            session_id,
            self.student.id,
            len(keys),
        )
        return keys

    def get_homework_progress(self, session_id: int) -> HomeworkProgress:
        """How many of the homework's exercises the student has solved.

        The exercise total is deterministic (counted from the uploaded text,
        no LLM needed). The solved count requires reading the whole
        conversation, so it is cached on the session's Performance row and
        only recomputed when new messages have arrived since the last check —
        cheap on every repeat view of the same session list."""
        session = self._get_session(session_id)
        if session.mode != SessionMode.HOMEWORK.value:
            raise HTTPException(
                status.HTTP_409_CONFLICT, "This is not a Homework Help session."
            )
        ctx = self._build_ctx(session)

        materials = ctx.materials.list_session_materials(session_id)
        homework_text = "\n\n".join(
            m.extracted_text
            for m in materials
            if m.status == "ready" and m.extracted_text
        )
        total = count_exercises(homework_text)

        messages = ctx.messages.get_specific_session_messages_history(session_id)
        message_count = len(messages)

        # A saved but unread/unsupported upload is still visible history. There
        # is no progress to cache yet, and a GET used to render the Files page
        # must not create a synthetic Performance row for it.
        if total == 0 and message_count == 0:
            return HomeworkProgress(total_exercises=0, solved_exercises=0)

        perf = ctx.performances.get_specific_session_performance(session_id)
        if (
            not settings.AGENT_ENABLED_HOMEWORK
            and perf is not None
            and perf.messages_synced == message_count
            and perf.total_questions == total
        ):
            return HomeworkProgress(
                total_exercises=total, solved_exercises=perf.score
            )

        solved = 0
        if settings.AGENT_ENABLED_HOMEWORK:
            from app.agent.stores import SessionStateStore

            valid_refs = {
                item.get("ref")
                for item in (session.homework_outline or [])
                if item.get("ref")
            }
            state = SessionStateStore(self.db).load(session_id)
            solved = min(total, len(state.solved_refs & valid_refs))
        elif total and message_count:
            transcript = [(m.role, m.content) for m in messages]
            try:
                solved = self.llm.summarize_homework_progress(
                    homework_text, transcript, total
                )
            except LLMError:
                # Best-effort: keep the last known count rather than failing
                # the whole session list over one summarization call.
                solved = perf.score if perf else 0

        level = (
            SuccessLevel.ACHIEVED
            if total and solved == total
            else SuccessLevel.PARTIALLY
            if solved
            else SuccessLevel.NOT_ACHIEVED
        )
        if perf is None:
            ctx.performances.add(
                Performance(
                    session_id=session_id,
                    success_level=level.value,
                    score=solved,
                    total_questions=total,
                    practice_sets=0,
                    messages_synced=message_count,
                )
            )
        else:
            perf.success_level = level.value
            perf.score = solved
            perf.total_questions = total
            perf.messages_synced = message_count
        self.db.commit()

        return HomeworkProgress(total_exercises=total, solved_exercises=solved)

    def get_agent_traces(self, session_id: int, run_id: str | None = None) -> list[dict]:
        """Read metadata-only agent traces for an owned session."""
        self._get_session(session_id)
        query = self.db.query(AgentTrace).filter(AgentTrace.session_id == session_id)
        if run_id:
            query = query.filter(AgentTrace.run_id == run_id)
        rows = query.order_by(AgentTrace.created_at.asc(), AgentTrace.id.asc()).all()
        return [
            {
                "run_id": row.run_id,
                "step": row.step,
                "kind": row.kind,
                "tool_name": row.tool_name,
                "args": row.args_json,
                "result": row.result_json,
                "duration_ms": row.duration_ms,
                "error": row.error,
                "created_at": row.created_at,
            }
            for row in rows
        ]

    def analyze_homework(self, session_id: int) -> TurnResult:
        """Generate the tutor's opening analysis of the uploaded homework.

        Safe to call again after the student adds another file — each call
        appends a fresh analysis turn rather than replacing the conversation."""
        session = self._get_session(session_id)
        if session.mode != SessionMode.HOMEWORK.value:
            raise HTTPException(
                status.HTTP_409_CONFLICT, "This is not a Homework Help session."
            )
        ctx = self._build_ctx(session)
        if settings.AGENT_ENABLED_HOMEWORK:
            homework_text = ctx._homework_text() or ""
            session.homework_outline = self._build_homework_outline(homework_text)
            for item in session.homework_outline:
                item["skill"] = session.subtopic or session.topic
        try:
            reply = ctx.state.generate_phase_opening_message(ctx)
        except LLMError as exc:
            raise self._llm_error(exc)
        if settings.AGENT_ENABLED_HOMEWORK and session.homework_outline:
            from app.agent.reducer import StateReducer
            from app.agent.schemas import ResponseTarget
            from app.agent.stores import SessionStateStore

            store = SessionStateStore(self.db)
            state = store.load(session.id)
            first = session.homework_outline[0]
            store.save(
                StateReducer.set_pending(
                    state, ResponseTarget(first["ref"], first.get("target_type", "exercise"))
                )
            )
        self.db.commit()
        return TurnResult(tutor_message=reply or "", phase=session.phase)

    @staticmethod
    def _build_homework_outline(homework_text: str) -> list[dict]:
        """Create stable targets and fill only deterministically computable keys."""
        import re

        from app.math.normalizer import canonical_fraction_str, parse_to_fraction
        from app.math.router import MathRouterService

        router = MathRouterService()
        outline = segment_exercises(homework_text)
        for item in outline:
            if item.get("expected_answer"):
                continue
            computed = router.try_compute_correct_answer(item["text"], "0")
            if computed.success and computed.canonical_answer:
                item["expected_answer"] = computed.canonical_answer
                continue
            if re.search(r"(?i)\b(?:simplify|reduce)\b", item["text"]):
                fractions = re.findall(r"-?\d+\s*/\s*\d+", item["text"])
                if len(fractions) == 1:
                    value = parse_to_fraction(fractions[0])
                    if value is not None:
                        item["expected_answer"] = canonical_fraction_str(value)
        return outline

    # ---- difficulty: initial pick (TEACHING opening) or mid-lesson change ----

    def set_lesson_difficulty(self, session_id: int, level: str) -> TurnResult:
        session = self._get_session(session_id)
        self._require_phase(session, LessonPhase.TEACHING)
        try:
            normalized = DifficultyLevel(level.strip().lower())
        except ValueError:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"Invalid difficulty level: '{level}'.",
            )

        ctx = self._build_ctx(session)
        is_first_pick = session.difficulty is None
        ctx.save_student_message_to_db(
            f"I'd like to {'start at' if is_first_pick else 'switch to'} the "
            f"{normalized.value} level."
        )
        session.difficulty = normalized.value

        try:
            if is_first_pick:
                reply = ctx.llm.generate_teaching_intro(ctx.build_tutor_context())
            else:
                reply = ctx.llm.generate_difficulty_change_message(
                    ctx.build_tutor_context(), normalized.value
                )
        except LLMError as exc:
            raise self._llm_error(exc)

        ctx.save_tutor_message_to_db(reply)
        self.db.commit()
        return TurnResult(tutor_message=reply, phase=session.phase)

    # ---- chat turn (TEACHING and SUMMARY phases) ----

    def send_student_message_and_get_tutor_reply(
        self, session_id: int, text: str, *, turn_id: str | None = None
    ) -> TurnResult:
        session = self._get_session(session_id)
        ctx = self._build_ctx(session, turn_id=turn_id)
        use_agent = isinstance(ctx.state, HomeworkHelpState) and _homework_agent_should_run(
            ctx, text
        )
        self._require_agent_turn_id(use_agent, turn_id)
        try:
            reply = ctx.state.generate_reply_to_student_message(ctx, text)
        except InvalidLessonAction as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
        except LLMError as exc:
            raise self._llm_error(exc)
        self.db.commit()
        return TurnResult(tutor_message=reply, phase=session.phase)

    # ---- streaming chat turn (token-by-token) ----

    def stream_student_message_and_get_tutor_reply(
        self,
        session_id: int,
        text: str,
        *,
        turn_id: str | None = None,
        ndjson_events: bool = False,
    ) -> Iterator[str]:
        """Stream the tutor's reply as text deltas.

        Phase is validated up front (so a wrong phase becomes a clean 409 before
        the stream starts). The student message is staged, the reply streamed,
        and both messages committed atomically once the stream completes — so a
        dropped stream leaves no orphaned student message."""
        session = self._get_session(session_id)
        ctx = self._build_ctx(session)
        if not isinstance(ctx.state, _ConversationalState):
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "You can only chat during a teaching, summary, or homework-help phase.",
            )

        use_agent = isinstance(ctx.state, HomeworkHelpState) and _homework_agent_should_run(
            ctx, text
        )
        self._require_agent_turn_id(use_agent, turn_id)
        ctx.save_student_message_to_db(text)
        self.db.flush()  # visible to the history query below, not yet committed
        tutor_ctx = ctx.build_tutor_context(text)
        annotated = _annotate_math(text)
        # Only grade during teaching (where the tutor asks interactive questions),
        # not during the summary chat.
        verdict = (
            verify_chat_answer(tutor_ctx.recent_messages, text, self.llm)
            if isinstance(ctx.state, TeachingState)
            else None
        )

        def generate() -> Iterator[str]:
            chunks: list[str] = []
            try:
                if ndjson_events:
                    yield json.dumps({"type": "stream_start"}) + "\n"
                if use_agent:
                    from app.agent.runner import AgentRunner

                    with self.db.begin_nested():
                        events = AgentRunner(
                            self.db, self.llm, self.student, session
                        ).run_stream(text, turn_id=turn_id)
                        for event in events:
                            if event.type == "text_delta":
                                delta = event.data or ""
                                chunks.append(delta)
                                if ndjson_events:
                                    yield json.dumps(
                                        {"type": "text_delta", "data": delta},
                                        ensure_ascii=False,
                                    ) + "\n"
                                else:
                                    yield delta
                            elif ndjson_events:
                                yield json.dumps(
                                    {
                                        "type": event.type,
                                        "tool_name": event.tool_name,
                                        "status": event.status,
                                    },
                                    ensure_ascii=False,
                                ) + "\n"
                else:
                    for delta in self.llm.chat_reply_stream(
                        tutor_ctx, annotated, verification=verdict
                    ):
                        chunks.append(delta)
                        if ndjson_events:
                            yield json.dumps(
                                {"type": "text_delta", "data": delta},
                                ensure_ascii=False,
                            ) + "\n"
                        else:
                            yield delta
            except GeneratorExit:
                # Closing a StreamingResponse injects GeneratorExit at the
                # current yield. Explicitly clear the request transaction so a
                # reused Session cannot later commit an orphaned message.
                self.db.rollback()
                raise
            except Exception:
                if chunks or not use_agent:
                    self.db.rollback()
                    raise
                log.exception(
                    "homework stream agent failed; using legacy stream session_id=%s",
                    session_id,
                )
                try:
                    for delta in self.llm.chat_reply_stream(tutor_ctx, annotated):
                        chunks.append(delta)
                        if ndjson_events:
                            yield json.dumps({"type": "text_delta", "data": delta}) + "\n"
                        else:
                            yield delta
                except BaseException:
                    self.db.rollback()
                    raise
            full = "".join(chunks).strip()
            if full:
                ctx.save_tutor_message_to_db(full)
            self.db.commit()
            if ndjson_events:
                yield json.dumps({"type": "done"}) + "\n"

        return generate()

    # ---- streaming chat turn with low-latency speech (NDJSON: text + audio) ----

    def stream_student_message_with_speech(
        self,
        session_id: int,
        text: str,
        voice: VoiceService,
        *,
        turn_id: str | None = None,
    ) -> Iterator[str]:
        """Stream the tutor reply as NDJSON events carrying both text deltas and
        per-chunk TTS audio, so the tutor starts speaking after the first short
        phrase instead of the whole reply.

        Setup (phase check, staging the student message, verdict) runs eagerly so
        a wrong phase becomes a clean 409 before the stream starts. Both messages
        are committed atomically once the stream completes; a dropped/aborted
        stream commits nothing, leaving no orphaned student message.

        Text streaming has absolute priority: TTS jobs run on a small thread pool
        and their audio is emitted strictly in chunk order, but futures are only
        drained non-blockingly between text deltas — block-waiting happens only
        after the LLM stream is finished. A TTS failure for one chunk never aborts
        the text stream."""
        session = self._get_session(session_id)
        ctx = self._build_ctx(session)
        if not isinstance(ctx.state, _ConversationalState):
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "You can only chat during a teaching, summary, or homework-help phase.",
            )

        use_agent = isinstance(ctx.state, HomeworkHelpState) and _homework_agent_should_run(
            ctx, text
        )
        self._require_agent_turn_id(use_agent, turn_id)
        ctx.save_student_message_to_db(text)
        self.db.flush()  # visible to the history query below, not yet committed
        tutor_ctx = ctx.build_tutor_context(text)
        annotated = _annotate_math(text)
        verdict = (
            verify_chat_answer(tutor_ctx.recent_messages, text, self.llm)
            if isinstance(ctx.state, TeachingState)
            else None
        )

        def generate() -> Iterator[str]:
            turn_start = time.perf_counter()
            committed = False
            timing: dict[str, float] = {}
            timing_lock = threading.Lock()

            def mark(name: str) -> None:
                # Metadata-only latency capture; safe to call from worker threads.
                with timing_lock:
                    if name not in timing:
                        timing[name] = (time.perf_counter() - turn_start) * 1000

            def ndjson(obj: dict) -> str:
                return json.dumps(obj, ensure_ascii=False) + "\n"

            def render_chunk_audio(chunk_text: str) -> bytes | None:
                # Runs on a worker thread: network TTS only, never touches the DB.
                mark("first_tts_request_started")
                try:
                    parts: list[bytes] = []
                    for b in voice.iter_speech_audio(chunk_text):
                        if b:
                            mark("first_audio_byte_received")
                            parts.append(b)
                    return b"".join(parts) if parts else None
                except VoiceServiceError:
                    log.warning(
                        "tts chunk failed in speech-stream session_id=%s", session_id
                    )
                    return None

            def emit_chunk(chunk_id: int, audio: bytes | None) -> Iterator[str]:
                if not audio:
                    return  # TTS failed or produced nothing — text already streamed
                mark("first_audio_delta_sent")
                yield ndjson({"type": "audio_start", "chunk_id": chunk_id})
                for i in range(0, len(audio), _AUDIO_DELTA_BYTES):
                    b64 = base64.b64encode(audio[i : i + _AUDIO_DELTA_BYTES]).decode("ascii")
                    yield ndjson(
                        {"type": "audio_delta", "chunk_id": chunk_id, "data": b64}
                    )
                yield ndjson({"type": "audio_end", "chunk_id": chunk_id})

            chunker = SpeechChunker()
            chunks_full: list[str] = []
            pending: list[concurrent.futures.Future] = []
            submitted = 0  # chunks sent to TTS (incl. ones that produced no audio)
            audio_seq = 0  # contiguous id sent to the client, only for real audio
            any_tts_failed = False
            executor = concurrent.futures.ThreadPoolExecutor(
                max_workers=MAX_CONCURRENT_TTS
            )
            try:
                # Open/flush the response immediately so the client confirms the
                # stream is live before the LLM's first token arrives. Unknown to
                # older clients — the frontend ignores event types it doesn't know.
                yield ndjson({"type": "stream_start"})
                def brain_events():
                    if use_agent:
                        from app.agent.runner import AgentRunner

                        try:
                            with self.db.begin_nested():
                                yield from AgentRunner(
                                    self.db, self.llm, self.student, session
                                ).run_stream(text, turn_id=turn_id)
                            return
                        except Exception:
                            log.exception(
                                "homework speech agent failed; using legacy stream session_id=%s",
                                session_id,
                            )
                    from app.llm.tooling import AgentStreamEvent

                    for legacy_delta in self.llm.chat_reply_stream(
                        tutor_ctx, annotated, verification=verdict
                    ):
                        yield AgentStreamEvent("text_delta", data=legacy_delta)

                for brain_event in brain_events():
                    if brain_event.type != "text_delta":
                        yield ndjson(
                            {
                                "type": brain_event.type,
                                "tool_name": brain_event.tool_name,
                                "status": brain_event.status,
                            }
                        )
                        continue
                    delta = brain_event.data or ""
                    chunks_full.append(delta)
                    mark("first_text_delta_sent")
                    yield ndjson({"type": "text_delta", "data": delta})
                    for ready in chunker.add(delta):
                        mark("first_tts_chunk_created")
                        submitted += 1
                        pending.append(executor.submit(render_chunk_audio, ready))
                    # Non-blocking, in-order drain: emit only already-finished audio
                    # from the front of the queue. Never wait while text may flow.
                    while pending and pending[0].done():
                        audio = pending.pop(0).result()
                        if audio is None:
                            any_tts_failed = True
                            continue
                        audio_seq += 1  # contiguous → no gaps for the client
                        for line in emit_chunk(audio_seq, audio):
                            yield line

                # LLM stream finished — now it's safe to block on remaining audio.
                last = chunker.flush()
                if last:
                    mark("first_tts_chunk_created")
                    submitted += 1
                    pending.append(executor.submit(render_chunk_audio, last))
                for fut in pending:
                    audio = fut.result()
                    if audio is None:
                        any_tts_failed = True
                        continue
                    audio_seq += 1
                    for line in emit_chunk(audio_seq, audio):
                        yield line
                pending.clear()

                full = "".join(chunks_full).strip()
                if full:
                    ctx.save_tutor_message_to_db(full)
                self.db.commit()
                committed = True
                mark("stream_done")
                log.info(
                    "speech-stream done session_id=%s total_chunks=%d "
                    "total_audio_chunks=%d any_tts_failed=%s timing_ms=%s",
                    session_id,
                    submitted,
                    audio_seq,
                    any_tts_failed,
                    {k: round(v, 1) for k, v in timing.items()},
                )
                yield ndjson({"type": "done"})
            except LLMError as exc:
                self.db.rollback()
                log.error(
                    "speech-stream llm error session_id=%s error=%s", session_id, exc
                )
                yield ndjson({"type": "error", "message": "Tutor service unavailable."})
            except Exception as exc:  # noqa: BLE001 - surface a clean event, not a 500
                self.db.rollback()
                log.error("speech-stream failed session_id=%s error=%s", session_id, exc)
                yield ndjson({"type": "error", "message": "Something went wrong."})
            finally:
                if not committed and self.db.in_transaction():
                    self.db.rollback()
                executor.shutdown(wait=False, cancel_futures=True)

        return generate()

    # ---- phase advance (TEACHING→PRE_PRACTICE_EXAMPLE, PRACTICE_SUMMARY→SUMMARY, SUMMARY→COMPLETED) ----

    def move_lesson_to_next_phase(self, session_id: int) -> PhaseResult:
        session = self._get_session(session_id)
        ctx = self._build_ctx(session)
        try:
            next_state = ctx.state.get_next_phase_state(ctx)
            ctx.move_to_next_phase_of_the_conversation(next_state.phase)
            content = ctx.state.generate_phase_opening_message(ctx)
        except InvalidLessonAction as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
        except LLMError as exc:
            raise self._llm_error(exc)
        self.db.commit()
        return PhaseResult(phase=session.phase, tutor_message=content)

    # ---- practice: start (PRE_PRACTICE_EXAMPLE → PRACTICE + set 1) ----

    def start_practice(self, session_id: int) -> PracticeStartResult:
        session = self._get_session(session_id)
        if session.phase not in (
            LessonPhase.PRE_PRACTICE_EXAMPLE.value,
            LessonPhase.PRACTICE.value,  # idempotent if already started
        ):
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Practice can only be started from the pre-practice example phase.",
            )
        ctx = self._build_ctx(session)

        # Transition to PRACTICE if not there yet
        if session.phase == LessonPhase.PRE_PRACTICE_EXAMPLE.value:
            ctx.move_to_next_phase_of_the_conversation(LessonPhase.PRACTICE)
            ctx.state.generate_phase_opening_message(ctx)

        if not isinstance(ctx.state, PracticeState):
            raise HTTPException(status.HTTP_409_CONFLICT, "Practice is not active.")

        try:
            questions = ctx.state.generate_practice_set(ctx, set_number=1)
        except LLMError as exc:
            raise self._llm_error(exc)

        self.db.commit()
        return PracticeStartResult(
            set_number=1,
            questions=[PracticeQuestionDTO.model_validate(q) for q in questions],
        )

    # ---- practice: submit answers for the current set ----

    def submit_practice_set(
        self, session_id: int, body: PracticeAnswersSubmit
    ) -> PracticeSubmitResult:
        session = self._get_session(session_id)
        self._require_practice_phase(session)
        ctx = self._build_ctx(session)

        if not isinstance(ctx.state, PracticeState):
            raise HTTPException(status.HTTP_409_CONFLICT, "No practice in progress.")

        answers = {item.question_id: item.answer for item in body.answers}
        if not answers:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "No answers submitted.")

        # Determine which set these answers belong to (by question IDs)
        first_qid = next(iter(answers))
        first_q = ctx.questions.get(first_qid)
        if first_q is None or first_q.session_id != session.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Question not found in this session.")
        set_number = first_q.set_number

        try:
            results = ctx.state.grade_and_save_set_answers(ctx, set_number, answers)
        except LLMError as exc:
            raise self._llm_error(exc)

        self.db.commit()

        grades = [
            GradedPracticeItem(
                question_id=q.id,
                question_text=q.question_text,
                difficulty=q.difficulty,
                set_number=q.set_number,
                student_answer=q.student_answer or "",
                is_correct=bool(q.is_correct),
                feedback=q.feedback or "",
                correct_answer=q.correct_answer,
                solution_steps=q.solution_steps,
                explanation=q.explanation,
            )
            for q, _ in results
        ]
        return PracticeSubmitResult(set_number=set_number, grades=grades)

    # ---- practice: generate next set ----

    def next_practice_set(self, session_id: int) -> PracticeStartResult:
        session = self._get_session(session_id)
        self._require_practice_phase(session)
        ctx = self._build_ctx(session)

        if not isinstance(ctx.state, PracticeState):
            raise HTTPException(status.HTTP_409_CONFLICT, "No practice in progress.")

        current_max = ctx.questions.get_latest_set_number(session_id)
        next_set = current_max + 1

        try:
            questions = ctx.state.generate_practice_set(ctx, set_number=next_set)
        except LLMError as exc:
            raise self._llm_error(exc)

        self.db.commit()
        return PracticeStartResult(
            set_number=next_set,
            questions=[PracticeQuestionDTO.model_validate(q) for q in questions],
        )

    # ---- practice: finish → PRACTICE_SUMMARY ----

    def finish_practice(self, session_id: int) -> PhaseResult:
        session = self._get_session(session_id)
        self._require_practice_phase(session)
        ctx = self._build_ctx(session)

        if not isinstance(ctx.state, PracticeState):
            raise HTTPException(status.HTTP_409_CONFLICT, "No practice in progress.")

        # Save aggregated performance before moving to summary
        ctx.state.finalize_practice_and_record_performance(ctx)

        ctx.move_to_next_phase_of_the_conversation(LessonPhase.PRACTICE_SUMMARY)
        self.db.commit()
        return PhaseResult(phase=LessonPhase.PRACTICE_SUMMARY.value)

    # ---- practice summary data ----

    def get_practice_summary(self, session_id: int) -> PracticeSummaryDTO:
        session = self._get_session(session_id)
        ctx = self._build_ctx(session)
        perf = ctx.performances.get_specific_session_performance(session_id)

        all_questions = ctx.questions.get_specific_session_questions(session_id)

        # Group by set_number
        sets_map: dict[int, list] = {}
        for q in all_questions:
            sn = q.set_number or 1
            sets_map.setdefault(sn, []).append(q)

        sets = [
            PracticeSetResult(
                set_number=sn,
                questions=[
                    GradedPracticeItem(
                        question_id=q.id,
                        question_text=q.question_text,
                        difficulty=q.difficulty,
                        set_number=q.set_number,
                        student_answer=q.student_answer or "",
                        is_correct=bool(q.is_correct) if q.is_correct is not None else False,
                        feedback=q.feedback or "",
                        correct_answer=q.correct_answer,
                        solution_steps=q.solution_steps,
                        explanation=q.explanation,
                    )
                    for q in sorted(qs, key=lambda x: x.difficulty)
                ],
            )
            for sn, qs in sorted(sets_map.items())
        ]

        total_correct = perf.score if perf else sum(1 for q in all_questions if q.is_correct)
        total_questions = perf.total_questions if perf else len(all_questions)

        return PracticeSummaryDTO(
            session_id=session_id,
            total_correct=total_correct,
            total_questions=total_questions,
            success_level=perf.success_level if perf else None,
            sets=sets,
        )

    # ---- final lesson summary (for summary page after the lesson) ----

    def get_or_generate_final_summary_text(self, session_id: int) -> str | None:
        """
        Return the lesson summary text for the summary page.

        Priority:
          1. Performance.summary_text already set (saved by SummaryState).
          2. Lazy-generate from LLM if the session is in SUMMARY or COMPLETED phase
             and no text was stored yet (e.g. legacy sessions).
        """
        session = self._get_session(session_id)
        ctx = self._build_ctx(session)
        perf = ctx.performances.get_specific_session_performance(session_id)

        if perf is None:
            return None

        if perf.summary_text:
            return perf.summary_text

        # Legacy / fallback: generate on demand if phase allows
        if session.phase in (LessonPhase.SUMMARY.value, LessonPhase.COMPLETED.value):
            try:
                text = self.llm.generate_lesson_summary(
                    ctx.build_tutor_context(),
                    perf.score,
                    perf.total_questions,
                )
                perf.summary_text = text
                self.db.commit()
                return text
            except LLMError:
                self.db.rollback()

        return None
