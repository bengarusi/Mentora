import logging

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.api.dependencies import get_tutor_service, get_voice_service
from app.schemas.material import HomeworkSessionCreate
from app.schemas.session import SessionResponse
from app.schemas.practice import (
    PracticeAnswersSubmit,
    PracticeStartResult,
    PracticeSubmitResult,
    PracticeSummaryDTO,
)
from app.schemas.tutor import (
    DifficultySelectRequest,
    HomeworkProgress,
    PhaseResult,
    TtsRequest,
    TtsResult,
    TurnRequest,
    TurnResult,
    VoiceTurnResult,
)
from app.services.tutor_service import TutorService
from app.services.voice_service import VoiceService, VoiceServiceError

log = logging.getLogger("app.api.tutorController")


class LessonSummaryResponse(BaseModel):
    session_id: int
    summary_text: str | None

router = APIRouter(prefix="/tutor", tags=["tutor"])


# ---------------------------------------------------------------------------
# Teaching phase chat
# ---------------------------------------------------------------------------

@router.post("/{session_id}/turn", response_model=TurnResult)
def send_student_message_and_get_tutor_reply(
    session_id: int,
    body: TurnRequest,
    tutor: TutorService = Depends(get_tutor_service),
):
    return tutor.send_student_message_and_get_tutor_reply(session_id, body.content)


@router.post("/{session_id}/turn/stream")
def stream_student_message_and_get_tutor_reply(
    session_id: int,
    body: TurnRequest,
    tutor: TutorService = Depends(get_tutor_service),
):
    """Stream the tutor's reply token-by-token as plain text chunks."""
    generator = tutor.stream_student_message_and_get_tutor_reply(
        session_id, body.content
    )
    return StreamingResponse(
        generator,
        media_type="text/plain; charset=utf-8",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/{session_id}/turn/speech-stream")
def stream_student_message_with_speech(
    session_id: int,
    body: TurnRequest,
    tutor: TutorService = Depends(get_tutor_service),
    voice: VoiceService = Depends(get_voice_service),
):
    """Low-latency turn: stream tutor text deltas AND per-chunk TTS audio as a
    single NDJSON response so speech starts after the first short phrase."""
    generator = tutor.stream_student_message_with_speech(
        session_id, body.content, voice
    )
    return StreamingResponse(
        generator,
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------------------
# TTS: convert any tutor text reply to speech (used by the typed-chat flow
# so the student hears every tutor message, not just voice-turn replies)
# ---------------------------------------------------------------------------

@router.post("/{session_id}/tts", response_model=TtsResult)
def speak_text(
    session_id: int,
    body: TtsRequest,
    tutor: TutorService = Depends(get_tutor_service),
    voice: VoiceService = Depends(get_voice_service),
):
    """Synthesize speech for an arbitrary tutor text. Session ownership is
    validated so the endpoint can't be used as a free anonymous TTS service."""
    tutor._get_session(session_id)  # raises 404 if the student doesn't own this session
    if not body.text.strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Text is empty.")
    try:
        audio_base64 = voice.synthesize_speech(body.text)
    except VoiceServiceError:
        log.warning("tts failed in /tts endpoint for session_id=%s", session_id)
        return TtsResult(audio_base64=None)
    return TtsResult(audio_base64=audio_base64)


# ---------------------------------------------------------------------------
# Voice turn: speech-in → existing tutor flow → speech-out
# ---------------------------------------------------------------------------

@router.post("/{session_id}/voice-turn", response_model=VoiceTurnResult)
async def voice_turn(
    session_id: int,
    file: UploadFile = File(...),
    tutor: TutorService = Depends(get_tutor_service),
    voice: VoiceService = Depends(get_voice_service),
):
    """Thin voice I/O wrapper: transcribe the uploaded audio, run the EXISTING
    non-streaming tutor turn on the transcript, then speak the tutor reply.

    The tutor brain is untouched here — this only adds speech-to-text on the way
    in and text-to-speech on the way out."""
    if file.content_type and not file.content_type.startswith("audio/"):
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            f"Expected an audio file, got content type '{file.content_type}'.",
        )

    audio_bytes = await file.read()
    if not audio_bytes:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "Uploaded audio file is empty."
        )

    # 1. Speech-to-text
    try:
        student_text = voice.transcribe_audio(audio_bytes, file.filename or "audio.webm")
    except VoiceServiceError as exc:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, f"Could not transcribe audio: {exc}"
        )
    if not student_text:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Could not understand the audio. Please try speaking again.",
        )

    # 2. Existing tutor flow (unchanged) — same method the typed chat uses.
    result = tutor.send_student_message_and_get_tutor_reply(session_id, student_text)

    # 3. Text-to-speech. A TTS failure must not break the tutor turn: we still
    #    return the text reply, just without audio.
    audio_base64: str | None = None
    try:
        audio_base64 = voice.synthesize_speech(result.tutor_message)
    except VoiceServiceError:
        log.warning("tts failed for session_id=%s; returning text-only reply", session_id)

    return VoiceTurnResult(
        student_text=student_text,
        tutor_message=result.tutor_message,
        phase=result.phase,
        audio_base64=audio_base64,
    )


# ---------------------------------------------------------------------------
# Homework Help: a dedicated session whose subject matter is an uploaded file
# ---------------------------------------------------------------------------

@router.post("/homework", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
def create_homework_session(
    body: HomeworkSessionCreate,
    tutor: TutorService = Depends(get_tutor_service),
):
    """Start an empty Homework Help session. The client then uploads the
    homework via /materials/homework/{id} and calls /analyze."""
    return tutor.create_homework_session(body)


@router.get("/homework", response_model=list[SessionResponse])
def list_homework_sessions(
    tutor: TutorService = Depends(get_tutor_service),
):
    """Homework Help sessions, newest first — these are deliberately absent
    from /sessions/ (which is about lessons), so this is how the Files page
    offers them for resuming."""
    return tutor.list_homework_sessions()


@router.post("/{session_id}/homework/analyze", response_model=TurnResult)
def analyze_homework(
    session_id: int,
    tutor: TutorService = Depends(get_tutor_service),
):
    """Have the tutor read the uploaded homework and open the conversation.
    Called again whenever the student adds another file."""
    return tutor.analyze_homework(session_id)


@router.get("/{session_id}/homework/progress", response_model=HomeworkProgress)
def get_homework_progress(
    session_id: int,
    tutor: TutorService = Depends(get_tutor_service),
):
    """How many exercises the student has solved out of the homework's total."""
    return tutor.get_homework_progress(session_id)


# ---------------------------------------------------------------------------
# Difficulty: initial pick (right after the lesson opens) or mid-lesson change
# via the "Increase difficulty" quick action
# ---------------------------------------------------------------------------

@router.post("/{session_id}/difficulty", response_model=TurnResult)
def set_lesson_difficulty(
    session_id: int,
    body: DifficultySelectRequest,
    tutor: TutorService = Depends(get_tutor_service),
):
    return tutor.set_lesson_difficulty(session_id, body.level)


# ---------------------------------------------------------------------------
# Phase advance: TEACHING→PRE_PRACTICE_EXAMPLE, PRACTICE_SUMMARY→SUMMARY, SUMMARY→COMPLETED
# ---------------------------------------------------------------------------

@router.post("/{session_id}/advance", response_model=PhaseResult)
def advance_lesson_to_next_phase(
    session_id: int,
    tutor: TutorService = Depends(get_tutor_service),
):
    return tutor.move_lesson_to_next_phase(session_id)


# ---------------------------------------------------------------------------
# Practice flow
# ---------------------------------------------------------------------------

@router.post("/{session_id}/practice/start", response_model=PracticeStartResult)
def start_practice(
    session_id: int,
    tutor: TutorService = Depends(get_tutor_service),
):
    """Transition PRE_PRACTICE_EXAMPLE → PRACTICE and return the first set of 3 questions."""
    return tutor.start_practice(session_id)


@router.post("/{session_id}/practice/submit", response_model=PracticeSubmitResult)
def submit_practice_set(
    session_id: int,
    body: PracticeAnswersSubmit,
    tutor: TutorService = Depends(get_tutor_service),
):
    """Grade all submitted answers for the current practice set."""
    return tutor.submit_practice_set(session_id, body)


@router.post("/{session_id}/practice/next", response_model=PracticeStartResult)
def next_practice_set(
    session_id: int,
    tutor: TutorService = Depends(get_tutor_service),
):
    """Generate the next practice set with increased difficulty."""
    return tutor.next_practice_set(session_id)


@router.post("/{session_id}/practice/finish", response_model=PhaseResult)
def finish_practice(
    session_id: int,
    tutor: TutorService = Depends(get_tutor_service),
):
    """Finalize practice, record performance, and move to PRACTICE_SUMMARY phase."""
    return tutor.finish_practice(session_id)


@router.get("/{session_id}/practice/summary", response_model=PracticeSummaryDTO)
def get_practice_summary(
    session_id: int,
    tutor: TutorService = Depends(get_tutor_service),
):
    """Return all practice questions with grading results, grouped by set."""
    return tutor.get_practice_summary(session_id)


@router.get("/{session_id}/lesson-summary", response_model=LessonSummaryResponse)
def get_lesson_summary(
    session_id: int,
    tutor: TutorService = Depends(get_tutor_service),
):
    """Return the final lesson summary text for the summary page."""
    text = tutor.get_or_generate_final_summary_text(session_id)
    return LessonSummaryResponse(session_id=session_id, summary_text=text)
