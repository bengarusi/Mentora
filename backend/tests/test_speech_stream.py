"""API tests for POST /tutor/{session_id}/turn/speech-stream.

The VoiceService is faked (it streams a couple of byte chunks instead of calling
OpenAI) so these tests pin down the NDJSON event protocol, audio ordering, and
the "TTS failure must not break text streaming" guarantee.
"""

import base64
import json
from collections.abc import Iterator

from app.api.dependencies import get_voice_service
from app.main import app
from app.services.voice_service import VoiceServiceError
from tests.conftest import auth_headers


class FakeStreamingVoiceService:
    """Stand-in for VoiceService: streams fixed bytes, or fails on demand."""

    def __init__(self, *, tts_error: bool = False, audio: bytes = b"\x00\x01\x02\x03"):
        self._tts_error = tts_error
        self._audio = audio

    def iter_speech_audio(self, text: str) -> Iterator[bytes]:
        if self._tts_error:
            raise VoiceServiceError("tts boom")
        # Two byte runs so multiple audio_delta events per chunk are exercised.
        yield self._audio
        yield self._audio


def _use_voice(fake: FakeStreamingVoiceService) -> None:
    app.dependency_overrides[get_voice_service] = lambda: fake


def _create_session(client, headers) -> int:
    resp = client.post(
        "/sessions/",
        json={
            "subject": "math",
            "topic": "Fractions",
            "subtopic": "Adding fractions",
            "goal_text": "Learn fractions",
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


def _parse_ndjson(text: str) -> list[dict]:
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def test_speech_stream_emits_text_then_ordered_audio_then_done(client):
    headers = auth_headers(client)
    session_id = _create_session(client, headers)
    _use_voice(FakeStreamingVoiceService())

    resp = client.post(
        f"/tutor/{session_id}/turn/speech-stream",
        json={"content": "hello tutor"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    events = _parse_ndjson(resp.text)
    types = [e["type"] for e in events]

    # Stream opens with stream_start, then text; terminates with a single done.
    assert types[0] == "stream_start"
    assert "text_delta" in types
    assert events[-1]["type"] == "done"
    assert types.count("done") == 1

    # The streamed text reconstructs the tutor reply (FakeLLM echoes the input).
    streamed_text = "".join(e["data"] for e in events if e["type"] == "text_delta")
    assert "hello tutor" in streamed_text

    # Audio chunk_ids are contiguous and strictly ascending (order preserved
    # even with MAX_CONCURRENT_TTS=2).
    starts = [e["chunk_id"] for e in events if e["type"] == "audio_start"]
    assert starts, "expected at least one audio chunk"
    assert starts == list(range(1, len(starts) + 1))

    # Per chunk: audio_start, then 1+ base64 audio_delta, then audio_end, in order.
    for cid in starts:
        chunk_types = [e["type"] for e in events if e.get("chunk_id") == cid]
        assert chunk_types[0] == "audio_start"
        assert chunk_types[-1] == "audio_end"
        assert chunk_types.count("audio_delta") >= 1
        for e in events:
            if e["type"] == "audio_delta" and e["chunk_id"] == cid:
                base64.b64decode(e["data"])  # must be valid base64


def test_speech_stream_tts_failure_still_streams_text(client):
    headers = auth_headers(client)
    session_id = _create_session(client, headers)
    _use_voice(FakeStreamingVoiceService(tts_error=True))

    resp = client.post(
        f"/tutor/{session_id}/turn/speech-stream",
        json={"content": "hello tutor"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    events = _parse_ndjson(resp.text)
    types = [e["type"] for e in events]

    # Text + done still arrive; no audio events when every TTS chunk fails.
    assert "text_delta" in types
    assert events[-1]["type"] == "done"
    assert "audio_start" not in types
    assert "audio_delta" not in types


def test_speech_stream_wrong_phase_returns_409(client):
    headers = auth_headers(client)
    session_id = _create_session(client, headers)
    _use_voice(FakeStreamingVoiceService())

    # TEACHING → PRE_PRACTICE_EXAMPLE: no longer a conversational phase.
    advance = client.post(f"/tutor/{session_id}/advance", headers=headers)
    assert advance.status_code == 200, advance.text

    resp = client.post(
        f"/tutor/{session_id}/turn/speech-stream",
        json={"content": "hi"},
        headers=headers,
    )
    assert resp.status_code == 409, resp.text


def test_speech_stream_requires_auth(client):
    _use_voice(FakeStreamingVoiceService())
    resp = client.post("/tutor/1/turn/speech-stream", json={"content": "hi"})
    assert resp.status_code == 401
