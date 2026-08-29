from __future__ import annotations

import base64
import io
import logging
import re
import time
from collections.abc import Iterator

from openai import OpenAI

from app.core.config import settings

log = logging.getLogger("app.services.voice_service")


class VoiceServiceError(Exception):
    """Raised when a speech-to-text or text-to-speech operation fails."""


class VoiceService:
    """Thin, self-contained audio I/O layer around the OpenAI audio APIs.

    It only converts audio <-> text. It knows nothing about lessons, sessions,
    prompts, or tutoring logic, which keeps the voice feature fully decoupled
    from the (still-evolving) tutor brain. Audio is processed entirely in memory:
    the backend never records from a microphone or plays sound locally.
    """

    def __init__(self) -> None:
        if not settings.OPENAI_API_KEY:
            raise VoiceServiceError("OPENAI_API_KEY is not configured")
        self.client = OpenAI(
            api_key=settings.OPENAI_API_KEY, timeout=30.0, max_retries=2
        )
        self.stt_model = settings.OPENAI_STT_MODEL
        self.tts_model = settings.OPENAI_TTS_MODEL
        self.tts_voice = settings.OPENAI_TTS_VOICE

    def transcribe_audio(
        self, audio_bytes: bytes, filename: str, context: str | None = None
    ) -> str:
        """Transcribe an uploaded audio file to text. Returns the trimmed
        transcript (may be empty if no speech was detected).

        *context* is the tutor's most recent message; passing it biases the
        decoder toward the words a valid answer would use (digits, number
        words) and away from off-topic hallucinations on noisy audio."""
        # OpenAI infers the format from the filename extension, so the upload
        # filename is passed through with the in-memory bytes.
        # Reject clips too short to contain speech: the model hallucinates
        # random text (foreign place names, etc.) on near-silent audio.
        if (
            settings.STT_MIN_AUDIO_BYTES
            and len(audio_bytes) < settings.STT_MIN_AUDIO_BYTES
        ):
            log.info("stt skipped: audio too short bytes=%d", len(audio_bytes))
            return ""
        buffer = io.BytesIO(audio_bytes)
        buffer.name = filename or "audio.webm"
        start = time.perf_counter()
        # Pin the language when configured; an empty setting lets the model
        # auto-detect (which can misread short clips as another language).
        extra = {}
        if settings.OPENAI_STT_LANGUAGE:
            extra["language"] = settings.OPENAI_STT_LANGUAGE
        # Bias decoding toward the expected domain (short spoken math answers),
        # which further suppresses off-topic hallucinations.
        prompt = (
            "A young student speaks a short answer to a math question, "
            "usually a number such as ten, twelve, or twenty-four."
        )
        if context:
            prompt = f"{prompt} The tutor just asked: {context.strip()}"
        extra["prompt"] = prompt
        try:
            result = self.client.audio.transcriptions.create(
                model=self.stt_model,
                file=buffer,
                temperature=0,
                **extra,
            )
        except Exception as exc:  # noqa: BLE001 - normalize SDK/network errors
            log.error(
                "stt failed model=%s bytes=%d error=%s",
                self.stt_model,
                len(audio_bytes),
                exc,
            )
            raise VoiceServiceError(str(exc)) from exc
        text = (getattr(result, "text", "") or "").strip()
        # Metadata only — never log the transcript text itself.
        log.info(
            "stt ok model=%s bytes=%d duration_ms=%.1f transcript_chars=%d",
            self.stt_model,
            len(audio_bytes),
            (time.perf_counter() - start) * 1000,
            len(text),
        )
        return text

    @staticmethod
    def _clean_for_speech(text: str) -> str:
        """Strip markdown formatting so TTS reads natural prose.

        Numbered list markers ("1. "), bullet points ("- "), heading hashes
        ("## "), blockquotes ("> "), and bold/italic asterisks are all
        invisible in rendered UI but would be read aloud as "one period",
        "hash hash", "asterisk", etc. if sent to TTS as-is."""
        # numbered list markers at start of line: "1. ", "12. "
        text = re.sub(r"^\d+\.\s+", "", text, flags=re.MULTILINE)
        # bullet / unordered list: "- " or "* " at start of line
        text = re.sub(r"^[-*]\s+", "", text, flags=re.MULTILINE)
        # blockquotes: "> "
        text = re.sub(r"^>\s*", "", text, flags=re.MULTILINE)
        # ATX headings: "## Heading"
        text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
        # bold / italic: **text**, *text*, ***text***
        text = re.sub(r"\*{1,3}(.+?)\*{1,3}", r"\1", text)
        # inline code: `code`
        text = re.sub(r"`([^`]+)`", r"\1", text)
        return text.strip()

    def synthesize_speech(self, text: str) -> str:
        """Convert tutor text to speech and return a base64-encoded mp3 string."""
        spoken = self._clean_for_speech(text)
        start = time.perf_counter()
        try:
            response = self.client.audio.speech.create(
                model=self.tts_model,
                voice=self.tts_voice,
                input=spoken,
                response_format="mp3",
            )
            audio_bytes = response.read()
        except Exception as exc:  # noqa: BLE001 - normalize SDK/network errors
            log.error(
                "tts failed model=%s text_chars=%d error=%s",
                self.tts_model,
                len(text),
                exc,
            )
            raise VoiceServiceError(str(exc)) from exc
        encoded = base64.b64encode(audio_bytes).decode("ascii")
        log.info(
            "tts ok model=%s voice=%s text_chars=%d duration_ms=%.1f audio_bytes=%d",
            self.tts_model,
            self.tts_voice,
            len(text),
            (time.perf_counter() - start) * 1000,
            len(audio_bytes),
        )
        return encoded

    def iter_speech_audio(self, text: str) -> Iterator[bytes]:
        """Stream tutor text to speech, yielding raw mp3 byte chunks as they arrive.

        Mirrors synthesize_speech but uses OpenAI's streaming response so the first
        bytes can be forwarded before the whole clip is rendered — the low-latency
        path used by the speech-stream tutor turn. Yields nothing if the cleaned
        text is empty. Errors are normalized to VoiceServiceError."""
        spoken = self._clean_for_speech(text)
        if not spoken:
            return
        start = time.perf_counter()
        total = 0
        try:
            with self.client.audio.speech.with_streaming_response.create(
                model=self.tts_model,
                voice=self.tts_voice,
                input=spoken,
                response_format="mp3",
            ) as response:
                for chunk in response.iter_bytes(chunk_size=4096):
                    if chunk:
                        total += len(chunk)
                        yield chunk
        except Exception as exc:  # noqa: BLE001 - normalize SDK/network errors
            log.error(
                "tts stream failed model=%s text_chars=%d error=%s",
                self.tts_model,
                len(text),
                exc,
            )
            raise VoiceServiceError(str(exc)) from exc
        log.info(
            "tts stream ok model=%s voice=%s text_chars=%d duration_ms=%.1f audio_bytes=%d",
            self.tts_model,
            self.tts_voice,
            len(text),
            (time.perf_counter() - start) * 1000,
            total,
        )
