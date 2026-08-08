"""Edge cases and failure modes for the Files feature — including the
streaming endpoints the UI actually uses."""

import pytest

from app.api.dependencies import get_storage
from app.core.enums import LessonPhase, MaterialKind, MaterialStatus
from app.files.chunking import chunk_text
from app.files.extraction import get_extractor
from app.files.retrieval import KeywordMaterialRetriever
from app.files.storage import LocalFileStorage
from app.main import app
from app.services.material_service import MaterialService
from tests.conftest import auth_headers, make_student


@pytest.fixture
def api(client, tmp_path):
    app.dependency_overrides[get_storage] = lambda: LocalFileStorage(tmp_path)
    yield client
    app.dependency_overrides.pop(get_storage, None)


@pytest.fixture
def storage(tmp_path):
    return LocalFileStorage(tmp_path)


@pytest.fixture
def service(db_session, storage):
    return MaterialService(
        db_session, make_student(db_session), storage, KeywordMaterialRetriever()
    )


# ---------------------------------------------------------------------------
# The streaming turn is what the UI calls — it must work in a homework session
# ---------------------------------------------------------------------------

def _homework_with_file(api, headers):
    session = api.post(
        "/tutor/homework", json={"subject": "math"}, headers=headers
    ).json()
    api.post(
        f"/materials/homework/{session['id']}",
        files={"file": ("hw.txt", b"Exercise 1: What is 1/2 + 1/4?", "text/plain")},
        headers=headers,
    )
    api.post(f"/tutor/{session['id']}/homework/analyze", headers=headers)
    return session


def test_text_stream_turn_works_in_a_homework_session(api):
    headers = auth_headers(api)
    session = _homework_with_file(api, headers)

    with api.stream(
        "POST",
        f"/tutor/{session['id']}/turn/stream",
        json={"content": "I think it is 3/4"},
        headers=headers,
    ) as resp:
        assert resp.status_code == 200
        body = "".join(resp.iter_text())
    assert body.strip()

    # The turn must be persisted, not just streamed.
    messages = api.get(f"/sessions/{session['id']}/messages", headers=headers).json()
    assert [m["role"] for m in messages] == ["tutor", "student", "tutor"]


def test_speech_stream_turn_works_in_a_homework_session(api, monkeypatch):
    """The default UI path (voice on) uses the NDJSON speech stream."""
    from app.api.dependencies import get_voice_service

    class FakeVoice:
        def iter_speech_audio(self, text):
            yield b"\x00fake-mp3"

    app.dependency_overrides[get_voice_service] = lambda: FakeVoice()
    try:
        headers = auth_headers(api)
        session = _homework_with_file(api, headers)
        with api.stream(
            "POST",
            f"/tutor/{session['id']}/turn/speech-stream",
            json={"content": "is it 3/4?"},
            headers=headers,
        ) as resp:
            assert resp.status_code == 200
            lines = [ln for ln in "".join(resp.iter_text()).split("\n") if ln.strip()]
        types = {__import__("json").loads(ln)["type"] for ln in lines}
        assert "text_delta" in types
        assert "done" in types
    finally:
        app.dependency_overrides.pop(get_voice_service, None)


def test_streaming_is_still_rejected_in_a_non_chat_phase(api):
    """Guard rails on the shared streaming path must survive the new state."""
    headers = auth_headers(api)
    lesson = api.post(
        "/sessions/",
        json={
            "subject": "math",
            "topic": "Fractions",
            "subtopic": "Adding fractions",
            "goal_text": "Learn fractions",
        },
        headers=headers,
    ).json()
    api.post(f"/tutor/{lesson['id']}/advance", headers=headers)  # → pre_practice

    resp = api.post(
        f"/tutor/{lesson['id']}/turn/stream",
        json={"content": "hello"},
        headers=headers,
    )
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# Homework without a readable file
# ---------------------------------------------------------------------------

def test_analyze_works_before_any_file_is_uploaded(api):
    """The student may click through before uploading; the tutor should ask for
    the file rather than error."""
    headers = auth_headers(api)
    session = api.post(
        "/tutor/homework", json={"subject": "math"}, headers=headers
    ).json()
    resp = api.post(f"/tutor/{session['id']}/homework/analyze", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["tutor_message"]


def test_unreadable_homework_does_not_become_context(api, db_session):
    headers = auth_headers(api)
    session = api.post(
        "/tutor/homework", json={"subject": "math"}, headers=headers
    ).json()
    resp = api.post(
        f"/materials/homework/{session['id']}",
        files={"file": ("scan.bin", b"\x00\x01\x02", "application/octet-stream")},
        headers=headers,
    )
    assert resp.json()["status"] == MaterialStatus.UNSUPPORTED.value
    # Analyzing anyway must not crash — it just has no homework text.
    assert api.post(
        f"/tutor/{session['id']}/homework/analyze", headers=headers
    ).status_code == 200


# ---------------------------------------------------------------------------
# Extraction / storage edge cases
# ---------------------------------------------------------------------------

def test_whitespace_only_file_is_marked_failed(service):
    material = service.upload_material(
        data=b"   \n\n   \t  ",
        filename="blank.txt",
        content_type="text/plain",
        kind=MaterialKind.STUDY_MATERIAL,
    )
    assert material.status == MaterialStatus.FAILED.value
    assert material.status_detail


def test_filename_cannot_escape_the_storage_root(service, tmp_path):
    """A hostile filename must not steer the write outside storage."""
    material = service.upload_material(
        data=b"hello",
        filename="../../../../etc/passwd.txt",
        content_type="text/plain",
        kind=MaterialKind.STUDY_MATERIAL,
    )
    stored = (tmp_path / material.storage_key).resolve()
    assert stored.is_relative_to(tmp_path.resolve())
    assert stored.exists()


def test_reprocess_marks_failed_when_the_stored_file_is_gone(service, storage):
    material = service.upload_material(
        data=b"Fractions are parts of a whole.",
        filename="notes.txt",
        content_type="text/plain",
        kind=MaterialKind.STUDY_MATERIAL,
    )
    storage.delete(material.storage_key)  # simulate lost blob
    again = service.reprocess(material.id)
    assert again.status == MaterialStatus.FAILED.value


def test_oversized_upload_is_rejected(service, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "MATERIAL_MAX_UPLOAD_MB", 1)
    with pytest.raises(Exception) as exc:
        service.upload_material(
            data=b"x" * (2 * 1024 * 1024),
            filename="big.txt",
            content_type="text/plain",
            kind=MaterialKind.STUDY_MATERIAL,
        )
    assert "413" in str(exc.value) or "smaller" in str(exc.value).lower()


def test_extension_is_used_when_the_browser_sends_a_generic_mime(service):
    """Browsers often send application/octet-stream; the extension must still
    pick the right extractor."""
    assert get_extractor("application/octet-stream", "notes.txt") is not None
    material = service.upload_material(
        data=b"Adding fractions keeps the denominator.",
        filename="notes.txt",
        content_type="application/octet-stream",
        kind=MaterialKind.STUDY_MATERIAL,
    )
    assert material.status == MaterialStatus.READY.value


def test_large_document_produces_many_ordered_chunks(service):
    body = "\n\n".join(f"Paragraph {i} about equivalent fractions." for i in range(300))
    material = service.upload_material(
        data=body.encode(),
        filename="long.txt",
        content_type="text/plain",
        kind=MaterialKind.STUDY_MATERIAL,
    )
    assert material.status == MaterialStatus.READY.value
    indexes = [c.chunk_index for c in material.chunks]
    assert len(indexes) > 1
    assert indexes == sorted(indexes) == list(range(len(indexes)))


def test_chunking_never_loses_the_start_or_end_of_a_document():
    text = "FIRST_MARKER\n\n" + ("filler paragraph. " * 400) + "\n\nLAST_MARKER"
    chunks = chunk_text(text, chunk_chars=400, overlap_chars=60)
    joined = " ".join(chunks)
    assert "FIRST_MARKER" in joined
    assert "LAST_MARKER" in joined


# ---------------------------------------------------------------------------
# Retrieval budget + tagging
# ---------------------------------------------------------------------------

def test_untagged_material_is_still_retrievable(service):
    service.upload_material(
        data=b"Equivalent fractions have the same value.",
        filename="untagged.txt",
        content_type="text/plain",
        kind=MaterialKind.STUDY_MATERIAL,
    )  # no subject/topic
    hits = service.retrieve_relevant(query="equivalent fractions", subject="math")
    assert hits


def test_retrieval_respects_the_limit(service):
    for i in range(10):
        service.upload_material(
            data=f"Note {i}: equivalent fractions have the same value.".encode(),
            filename=f"n{i}.txt",
            content_type="text/plain",
            kind=MaterialKind.STUDY_MATERIAL,
            subject="math",
        )
    assert len(service.retrieve_relevant(query="equivalent fractions", limit=3)) <= 3


def test_lesson_context_caps_material_at_the_char_budget(db_session, storage, monkeypatch):
    """A long upload must not crowd out the lesson in the prompt."""
    from app.core.config import settings
    from app.lesson.context import LessonContext
    from app.models.session import LessonSession
    from app.core.enums import SessionStatus
    from tests.fake_llm import FakeLLMProvider

    monkeypatch.setattr(settings, "MATERIAL_CONTEXT_CHAR_BUDGET", 200)
    student = make_student(db_session)
    svc = MaterialService(db_session, student, storage, KeywordMaterialRetriever())
    svc.upload_material(
        data=("equivalent fractions " * 2000).encode(),
        filename="huge.txt",
        content_type="text/plain",
        kind=MaterialKind.STUDY_MATERIAL,
        subject="math",
    )

    session = LessonSession(
        student_id=student.id,
        subject="math",
        topic="Fractions",
        subtopic="Equivalent fractions",
        goal_text="Learn fractions",
        status=SessionStatus.ACTIVE.value,
        phase=LessonPhase.TEACHING.value,
        mode="lesson",
    )
    db_session.add(session)
    db_session.commit()

    ctx = LessonContext(db_session, session, student, FakeLLMProvider())
    tutor_ctx = ctx.build_tutor_context("equivalent fractions")
    total = sum(len(e.content) for e in tutor_ctx.material_excerpts)
    assert 0 < total <= 200
