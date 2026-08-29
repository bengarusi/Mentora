"""API tests for POST /tutor/{session_id}/voice-turn.

The VoiceService (OpenAI audio I/O) is faked so no network/audio is involved;
these tests pin down the endpoint's wiring and its error handling around the
existing tutor flow.
"""

from app.api.dependencies import get_voice_service
from app.main import app
from app.services.voice_service import VoiceServiceError
from tests.conftest import auth_headers


class FakeVoiceService:
    """Configurable stand-in for VoiceService — no OpenAI calls."""

    def __init__(
        self,
        *,
        transcript: str = "what is one plus one",
        audio: str | None = "ZmFrZS1tcDM=",  # base64("fake-mp3")
        stt_error: bool = False,
        tts_error: bool = False,
    ):
        self._transcript = transcript
        self._audio = audio
        self._stt_error = stt_error
        self._tts_error = tts_error

    def transcribe_audio(
        self, audio_bytes: bytes, filename: str, context: str | None = None
    ) -> str:
        if self._stt_error:
            raise VoiceServiceError("stt boom")
        return self._transcript

    def synthesize_speech(self, text: str) -> str:
        if self._tts_error:
            raise VoiceServiceError("tts boom")
        assert self._audio is not None
        return self._audio


def _use_voice(fake: FakeVoiceService) -> None:
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


def _audio_file(content: bytes = b"fake-audio-bytes", content_type: str = "audio/webm"):
    return {"file": ("recording.webm", content, content_type)}


def test_voice_turn_returns_transcript_reply_and_audio(client):
    headers = auth_headers(client)
    session_id = _create_session(client, headers)
    _use_voice(FakeVoiceService(transcript="hello tutor", audio="ZmFrZS1tcDM="))

    resp = client.post(
        f"/tutor/{session_id}/voice-turn", files=_audio_file(), headers=headers
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["student_text"] == "hello tutor"
    # Reply comes from the EXISTING tutor flow (FakeLLMProvider echoes the input).
    assert "hello tutor" in body["tutor_message"]
    assert body["phase"] == "teaching"
    assert body["audio_base64"] == "ZmFrZS1tcDM="


def test_voice_turn_empty_transcription_returns_422(client):
    headers = auth_headers(client)
    session_id = _create_session(client, headers)
    # VoiceService strips its output, so a silent recording yields "".
    _use_voice(FakeVoiceService(transcript=""))

    resp = client.post(
        f"/tutor/{session_id}/voice-turn", files=_audio_file(), headers=headers
    )

    assert resp.status_code == 422, resp.text


def test_voice_turn_tts_failure_still_returns_text_reply(client):
    headers = auth_headers(client)
    session_id = _create_session(client, headers)
    _use_voice(FakeVoiceService(transcript="hi", tts_error=True))

    resp = client.post(
        f"/tutor/{session_id}/voice-turn", files=_audio_file(), headers=headers
    )

    # A TTS failure must NOT fail the tutor turn — text reply still returns.
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["student_text"] == "hi"
    assert body["tutor_message"]
    assert body["audio_base64"] is None


def test_voice_turn_transcription_failure_returns_502(client):
    headers = auth_headers(client)
    session_id = _create_session(client, headers)
    _use_voice(FakeVoiceService(stt_error=True))

    resp = client.post(
        f"/tutor/{session_id}/voice-turn", files=_audio_file(), headers=headers
    )

    assert resp.status_code == 502, resp.text


def test_voice_turn_rejects_non_audio_content_type(client):
    headers = auth_headers(client)
    session_id = _create_session(client, headers)
    _use_voice(FakeVoiceService())

    resp = client.post(
        f"/tutor/{session_id}/voice-turn",
        files={"file": ("notes.txt", b"not audio", "text/plain")},
        headers=headers,
    )

    assert resp.status_code == 415, resp.text


def test_voice_turn_empty_file_returns_422(client):
    headers = auth_headers(client)
    session_id = _create_session(client, headers)
    _use_voice(FakeVoiceService())

    resp = client.post(
        f"/tutor/{session_id}/voice-turn",
        files=_audio_file(content=b""),
        headers=headers,
    )

    assert resp.status_code == 422, resp.text


def test_voice_turn_requires_auth(client):
    _use_voice(FakeVoiceService())
    resp = client.post("/tutor/1/voice-turn", files=_audio_file())
    assert resp.status_code == 401
