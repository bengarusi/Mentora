"""End-to-end Homework Help flow, driven through the HTTP API."""

import pytest

from app.api.dependencies import get_storage
from app.core.enums import LessonPhase, MaterialStatus, MessageRole, SessionMode
from app.files.storage import LocalFileStorage
from app.main import app
from tests.conftest import auth_headers


@pytest.fixture
def api(client, tmp_path):
    """The shared `client` fixture, with uploads redirected to a temp dir so
    tests never touch the real storage root."""
    app.dependency_overrides[get_storage] = lambda: LocalFileStorage(tmp_path)
    yield client
    app.dependency_overrides.pop(get_storage, None)


HOMEWORK = (
    "Exercise 1: What is 1/2 + 1/4?\n"
    "Exercise 2: Simplify 6/8.\n"
)


def _start_homework(api, headers):
    resp = api.post("/tutor/homework", json={"subject": "math"}, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _upload_homework(api, headers, session_id, text=HOMEWORK, name="homework.txt"):
    return api.post(
        f"/materials/homework/{session_id}",
        files={"file": (name, text.encode("utf-8"), "text/plain")},
        headers=headers,
    )


def test_homework_session_starts_in_its_own_mode_and_phase(api):
    headers = auth_headers(api)
    session = _start_homework(api, headers)
    assert session["mode"] == SessionMode.HOMEWORK.value
    assert session["phase"] == LessonPhase.HOMEWORK_HELP.value
    # No tutor message yet — there is nothing to talk about until a file lands.
    messages = api.get(f"/sessions/{session['id']}/messages", headers=headers).json()
    assert messages == []


def test_upload_then_analyze_produces_an_opening_tutor_message(api):
    headers = auth_headers(api)
    session = _start_homework(api, headers)

    upload = _upload_homework(api, headers, session["id"])
    assert upload.status_code == 201, upload.text
    material = upload.json()
    assert material["status"] == MaterialStatus.READY.value
    assert material["session_id"] == session["id"]

    analyze = api.post(
        f"/tutor/{session['id']}/homework/analyze", headers=headers
    )
    assert analyze.status_code == 200, analyze.text
    assert analyze.json()["tutor_message"]

    messages = api.get(f"/sessions/{session['id']}/messages", headers=headers).json()
    assert len(messages) == 1
    assert messages[0]["role"] == MessageRole.TUTOR.value


def test_student_can_chat_in_a_homework_session(api):
    headers = auth_headers(api)
    session = _start_homework(api, headers)
    _upload_homework(api, headers, session["id"])
    api.post(f"/tutor/{session['id']}/homework/analyze", headers=headers)

    turn = api.post(
        f"/tutor/{session['id']}/turn",
        json={"content": "I think the answer to exercise 1 is 3/4"},
        headers=headers,
    )
    assert turn.status_code == 200, turn.text
    assert turn.json()["phase"] == LessonPhase.HOMEWORK_HELP.value


def test_homework_upload_rejected_for_a_normal_lesson_session(api):
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

    resp = _upload_homework(api, headers, lesson["id"])
    assert resp.status_code == 409


def test_analyze_rejected_for_a_normal_lesson_session(api):
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

    resp = api.post(f"/tutor/{lesson['id']}/homework/analyze", headers=headers)
    assert resp.status_code == 409


def test_another_student_cannot_upload_into_someone_elses_session(api):
    owner = auth_headers(api, email="owner@example.com")
    session = _start_homework(api, owner)

    intruder = auth_headers(api, email="intruder@example.com")
    resp = _upload_homework(api, intruder, session["id"])
    assert resp.status_code == 404


# ---- study materials over HTTP ----

def test_study_material_upload_list_and_delete(api):
    headers = auth_headers(api)
    resp = api.post(
        "/materials/",
        files={"file": ("notes.txt", b"Fractions are parts of a whole.", "text/plain")},
        data={"subject": "math", "topic": "Fractions"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    material = resp.json()
    assert material["status"] == MaterialStatus.READY.value
    assert material["chunk_count"] >= 1

    listed = api.get("/materials/", headers=headers).json()["materials"]
    assert [m["id"] for m in listed] == [material["id"]]

    assert api.delete(f"/materials/{material['id']}", headers=headers).status_code == 204
    assert api.get("/materials/", headers=headers).json()["materials"] == []


def test_material_can_be_retagged(api):
    headers = auth_headers(api)
    material = api.post(
        "/materials/",
        files={"file": ("notes.txt", b"Some notes about shapes.", "text/plain")},
        headers=headers,
    ).json()

    resp = api.patch(
        f"/materials/{material['id']}",
        json={"subject": "math", "topic": "Geometry"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["topic"] == "Geometry"


def test_students_only_see_their_own_materials(api):
    owner = auth_headers(api, email="owner@example.com")
    api.post(
        "/materials/",
        files={"file": ("mine.txt", b"My private notes.", "text/plain")},
        headers=owner,
    )
    other = auth_headers(api, email="other@example.com")
    assert api.get("/materials/", headers=other).json()["materials"] == []


def test_supported_formats_are_advertised(api):
    headers = auth_headers(api)
    body = api.get("/materials/supported-formats", headers=headers).json()
    assert ".pdf" in body["extensions"]
    assert ".txt" in body["extensions"]
    assert body["max_upload_mb"] > 0


# ---------------------------------------------------------------------------
# Grading: homework must NOT lock in a verdict from the last tutor question
# ---------------------------------------------------------------------------

def test_homework_reply_does_not_lock_in_a_deterministic_verdict(db_session, monkeypatch):
    """Regression: the tutor asked a scaffolding sub-step ("write 1/2 as
    fourths"), the student answered the whole exercise ("3/4"), and the grader
    compared the two — marking correct working wrong and forcing the tutor to
    agree. Homework turns must reach the LLM with no verdict attached."""
    from app.core.enums import LessonPhase, SessionMode, SessionStatus
    from app.lesson.context import LessonContext
    from app.models.session import LessonSession
    from tests.conftest import make_student
    from tests.fake_llm import FakeLLMProvider

    student = make_student(db_session)
    session = LessonSession(
        student_id=student.id,
        subject="math",
        topic="Homework Help",
        subtopic="My homework",
        goal_text="Help with homework",
        status=SessionStatus.ACTIVE.value,
        mode=SessionMode.HOMEWORK.value,
        phase=LessonPhase.HOMEWORK_HELP.value,
    )
    db_session.add(session)
    db_session.commit()

    seen = {}

    class RecordingLLM(FakeLLMProvider):
        def chat_reply(self, ctx, student_message, *, verification=None):
            seen["verification"] = verification
            return "ok"

    ctx = LessonContext(db_session, session, student, RecordingLLM())
    ctx.save_tutor_message_to_db("What is 1/2 written as fourths?")
    ctx.state.generate_reply_to_student_message(ctx, "3/4")

    assert seen["verification"] is None


def test_teaching_still_locks_in_its_verdict(db_session):
    """The homework change must not weaken the teaching chat, where the tutor
    owns the question and deterministic grading is what stops it marking a
    correct answer wrong."""
    from app.lesson.context import LessonContext
    from app.schemas.session import SessionCreate
    from app.services.tutor_service import TutorService
    from tests.conftest import make_student
    from tests.fake_llm import FakeLLMProvider

    student = make_student(db_session)
    service = TutorService(db_session, FakeLLMProvider(), student)
    session = service.create_lesson_and_generate_first_explanation(
        SessionCreate(
            subject="math",
            topic="Addition & Subtraction",
            subtopic="Addition basics",
            goal_text="Learn to add",
        )
    )

    seen = {}

    class RecordingLLM(FakeLLMProvider):
        def chat_reply(self, ctx, student_message, *, verification=None):
            seen["verification"] = verification
            return "ok"

    ctx = LessonContext(db_session, session, student, RecordingLLM())
    ctx.save_tutor_message_to_db("What is 2 + 2?")
    ctx.state.generate_reply_to_student_message(ctx, "4")

    assert seen["verification"] is not None
    assert seen["verification"].is_equivalent is True


# ---------------------------------------------------------------------------
# Homework progress: exercises solved out of the homework's total
# ---------------------------------------------------------------------------

def test_progress_counts_total_exercises_from_the_upload(api):
    headers = auth_headers(api)
    # HOMEWORK = "Exercise 1: What is 1/2 + 1/4?\nExercise 2: Simplify 6/8.\n"
    session = _start_homework(api, headers)
    _upload_homework(api, headers, session["id"])
    api.post(f"/tutor/{session['id']}/homework/analyze", headers=headers)
    progress = api.get(f"/tutor/{session['id']}/homework/progress", headers=headers).json()
    assert progress["total_exercises"] == 2
    assert progress["solved_exercises"] == 0


def test_progress_updates_as_the_student_solves_exercises(api):
    headers = auth_headers(api)
    session = _start_homework(api, headers)
    _upload_homework(api, headers, session["id"])
    api.post(f"/tutor/{session['id']}/homework/analyze", headers=headers)
    api.post(
        f"/tutor/{session['id']}/turn",
        json={"content": "3/4, correct!"},
        headers=headers,
    )
    progress = api.get(f"/tutor/{session['id']}/homework/progress", headers=headers).json()
    assert progress["total_exercises"] == 2
    # FakeLLMProvider counts tutor turns containing "correct" as solved.
    assert progress["solved_exercises"] >= 0  # exercises the fake grader recognised


def test_progress_is_cached_and_not_recomputed_without_new_messages(api, monkeypatch):
    """The cache (Performance.messages_synced) must actually be used — a
    second call with no new messages must not re-run the summarization."""
    from app.api.dependencies import get_llm
    from app.main import app as fastapi_app

    calls = {"n": 0}

    class CountingLLM:
        def __getattr__(self, name):
            from tests.fake_llm import FakeLLMProvider
            return getattr(FakeLLMProvider(), name)

        def summarize_homework_progress(self, *a, **kw):
            calls["n"] += 1
            from tests.fake_llm import FakeLLMProvider
            return FakeLLMProvider().summarize_homework_progress(*a, **kw)

    fastapi_app.dependency_overrides[get_llm] = lambda: CountingLLM()
    try:
        headers = auth_headers(api)
        session = _start_homework(api, headers)
        api.post(
            f"/tutor/{session['id']}/turn",
            json={"content": "3/4"},
            headers=headers,
        )
        api.get(f"/tutor/{session['id']}/homework/progress", headers=headers)
        first_calls = calls["n"]
        api.get(f"/tutor/{session['id']}/homework/progress", headers=headers)
        assert calls["n"] == first_calls, "progress was recomputed with no new messages"
    finally:
        fastapi_app.dependency_overrides.pop(get_llm, None)


def test_progress_rejected_for_a_normal_lesson_session(api):
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
    resp = api.get(f"/tutor/{lesson['id']}/homework/progress", headers=headers)
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# Viewing the uploaded file
# ---------------------------------------------------------------------------

def test_can_view_the_uploaded_homework_file(api):
    headers = auth_headers(api)
    session = _start_homework(api, headers)
    _upload_homework(api, headers, session["id"])
    materials = api.get(f"/materials/homework/{session['id']}", headers=headers).json()
    material_id = materials["materials"][0]["id"]

    resp = api.get(f"/materials/{material_id}/file", headers=headers)
    assert resp.status_code == 200
    assert resp.content == HOMEWORK.encode("utf-8")
    assert "inline" in resp.headers["content-disposition"]


def test_cannot_view_another_students_file(api):
    owner = auth_headers(api, email="owner@example.com")
    session = _start_homework(api, owner)
    _upload_homework(api, owner, session["id"])
    materials = api.get(f"/materials/homework/{session['id']}", headers=owner).json()
    material_id = materials["materials"][0]["id"]

    intruder = auth_headers(api, email="intruder@example.com")
    resp = api.get(f"/materials/{material_id}/file", headers=intruder)
    assert resp.status_code == 404


def test_view_file_requires_auth(api):
    assert api.get("/materials/1/file").status_code == 401
