"""Model smoke-test for Mentora backend.

Run from the backend/ directory so pydantic-settings picks up .env:

    python scripts/check_openai_models.py

Prints OK / BLOCKED for each model and exits with code 0 if everything
passes, or 1 if any model access fails.  The API key is never printed.
"""

from __future__ import annotations

import sys

# Ensure 'app' is importable from backend/
sys.path.insert(0, ".")

from openai import OpenAI  # noqa: E402
from app.core.config import settings  # noqa: E402

_BLOCKED_MSG = (
    "  BLOCKED — Project does not have access to this model.\n"
    "  Fix: OpenAI Dashboard → your project → Settings → Limits → Model access"
)

all_ok = True


def _section(title: str) -> None:
    print(f"\n{'-' * 50}\n{title}")


def _is_reasoning_model(model: str) -> bool:
    """Match the same heuristic as OpenAIProvider so the smoke test uses the
    right token parameter for gpt-5.x and o-series models."""
    return "gpt-5" in model or model.startswith("o1") or model.startswith("o3")


def check_tutor_model() -> None:
    global all_ok
    _section(f"OPENAI_MODEL (tutor brain): {settings.OPENAI_MODEL}")
    client = OpenAI(api_key=settings.OPENAI_API_KEY, timeout=20, max_retries=0)
    # gpt-5.x / o-series require max_completion_tokens; older models use max_tokens.
    token_kwarg = (
        {"max_completion_tokens": 10}
        if _is_reasoning_model(settings.OPENAI_MODEL)
        else {"max_tokens": 10}
    )
    try:
        resp = client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[{"role": "user", "content": "Say OK"}],
            **token_kwarg,
        )
        reply = (resp.choices[0].message.content or "").strip()
        print(f"  OK -- model replied: {reply!r}")
    except Exception as exc:
        msg = str(exc)
        if "403" in msg or "model_not_found" in msg or "access" in msg.lower():
            print(_BLOCKED_MSG)
        else:
            print(f"  ERROR -- {exc}")
        all_ok = False


# Module-level storage so check_tts_model() can pass audio to check_stt_model().
_tts_audio_bytes: bytes | None = None


def check_tts_model() -> None:
    global all_ok, _tts_audio_bytes
    _section(
        f"OPENAI_TTS_MODEL: {settings.OPENAI_TTS_MODEL} "
        f"/ voice: {settings.OPENAI_TTS_VOICE}"
    )
    client = OpenAI(api_key=settings.OPENAI_API_KEY, timeout=20, max_retries=0)
    try:
        resp = client.audio.speech.create(
            model=settings.OPENAI_TTS_MODEL,
            voice=settings.OPENAI_TTS_VOICE,
            input="Hello",
            response_format="mp3",
        )
        _tts_audio_bytes = resp.read()
        print(f"  OK -- received {len(_tts_audio_bytes)} bytes of mp3")
    except Exception as exc:
        msg = str(exc)
        if "403" in msg or "model_not_found" in msg or "access" in msg.lower():
            print(_BLOCKED_MSG)
        else:
            print(f"  ERROR -- {exc}")
        all_ok = False


def check_stt_model() -> None:
    import io, os  # noqa: E401
    global all_ok
    _section(f"OPENAI_STT_MODEL (transcription): {settings.OPENAI_STT_MODEL}")

    # Prefer: transcribe the TTS audio we just generated (live round-trip test).
    # Fallback: a local test file.  Skip with config note if neither is available.
    audio_bytes: bytes | None = _tts_audio_bytes
    filename = "hello.mp3"

    if audio_bytes is None:
        for candidate in ("test_audio.webm", "test_audio.mp3"):
            p = os.path.join(os.path.dirname(__file__), candidate)
            if os.path.exists(p):
                with open(p, "rb") as f:
                    audio_bytes = f.read()
                filename = candidate
                break

    if audio_bytes is None:
        print(
            "  Configured -- no audio to transcribe right now.\n"
            "  Use the browser voice flow to test STT end-to-end."
        )
        return

    client = OpenAI(api_key=settings.OPENAI_API_KEY, timeout=30, max_retries=0)
    try:
        buf = io.BytesIO(audio_bytes)
        buf.name = filename
        result = client.audio.transcriptions.create(
            model=settings.OPENAI_STT_MODEL, file=buf
        )
        transcript = (getattr(result, "text", "") or "").strip()
        print(f"  OK -- transcript: {transcript!r}")
    except Exception as exc:
        msg = str(exc)
        if "403" in msg or "model_not_found" in msg or "access" in msg.lower():
            print(_BLOCKED_MSG)
        else:
            print(f"  ERROR -- {exc}")
        all_ok = False


if __name__ == "__main__":
    print("Mentora model smoke-test")
    print("API key: [hidden]")

    check_tutor_model()
    check_tts_model()
    check_stt_model()

    print(f"\n{'-' * 50}")
    if all_ok:
        print("All checked models: OK")
        sys.exit(0)
    else:
        print("One or more models BLOCKED — see above for fix instructions.")
        sys.exit(1)
