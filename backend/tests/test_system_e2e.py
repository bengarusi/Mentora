"""Whole-system journeys over HTTP, including how the new Files feature
interacts with the pre-existing lesson and progress flows."""

import pytest

from app.api.dependencies import get_storage
from app.core.enums import LessonPhase, SessionMode
from app.files.storage import LocalFileStorage
from app.main import app
from tests.conftest import auth_headers


@pytest.fixture
def api(client, tmp_path):
    app.dependency_overrides[get_storage] = lambda: LocalFileStorage(tmp_path)
    yield client
    app.dependency_overrides.pop(get_storage, None)


def _start_lesson(api, headers, topic="Fractions", subtopic="Adding fractions"):
    return api.post(
        "/sessions/",
        json={
            "subject": "math",
            "topic": topic,
            "subtopic": subtopic,
            "goal_text": f"Learn {subtopic}",
        },
        headers=headers,
    ).json()


def _start_homework(api, headers, text=b"Exercise 1: What is 1/2 + 1/4?"):
    session = api.post(
        "/tutor/homework", json={"subject": "math"}, headers=headers
    ).json()
    api.post(
        f"/materials/homework/{session['id']}",
        files={"file": ("hw.txt", text, "text/plain")},
        headers=headers,
    )
    api.post(f"/tutor/{session['id']}/homework/analyze", headers=headers)
    return session


# ---------------------------------------------------------------------------
# The original lesson journey must still work end to end
# ---------------------------------------------------------------------------

def test_full_lesson_journey_still_works(api):
    headers = auth_headers(api)
    session = _start_lesson(api, headers)
    sid = session["id"]
    assert session["mode"] == SessionMode.LESSON.value

    # Difficulty is asked first, before any teaching content.
    assert api.post(
        f"/tutor/{sid}/difficulty", json={"level": "easy"}, headers=headers
    ).status_code == 200

    assert api.post(
        f"/tutor/{sid}/turn", json={"content": "I think it is 3/4"}, headers=headers
    ).status_code == 200

    # teaching → pre-practice example → practice
    assert api.post(f"/tutor/{sid}/advance", headers=headers).json()["phase"] == (
        LessonPhase.PRE_PRACTICE_EXAMPLE.value
    )
    practice = api.post(f"/tutor/{sid}/practice/start", headers=headers).json()
    assert len(practice["questions"]) == 3

    answers = [
        {"question_id": q["id"], "answer": f"correct{q['difficulty']}"}
        for q in practice["questions"]
    ]
    graded = api.post(
        f"/tutor/{sid}/practice/submit", json={"answers": answers}, headers=headers
    ).json()
    assert all(g["is_correct"] for g in graded["grades"])

    api.post(f"/tutor/{sid}/practice/finish", headers=headers)
    assert api.post(f"/tutor/{sid}/advance", headers=headers).json()["phase"] == (
        LessonPhase.SUMMARY.value
    )
    summary = api.get(f"/tutor/{sid}/lesson-summary", headers=headers).json()
    assert summary["summary_text"]


# ---------------------------------------------------------------------------
# Homework sessions must not leak into lesson tracking
# ---------------------------------------------------------------------------

def test_homework_sessions_do_not_appear_in_the_lesson_list(api):
    headers = auth_headers(api)
    lesson = _start_lesson(api, headers)
    _start_homework(api, headers)

    listed = api.get("/sessions/", headers=headers).json()
    assert [s["id"] for s in listed] == [lesson["id"]], (
        "Homework Help sessions are not lessons and must not show up in "
        "'My Lessons' — opening one there would render the lesson UI for a "
        "session that has no phases."
    )


def test_homework_sessions_do_not_inflate_progress_stats(api):
    headers = auth_headers(api)
    _start_lesson(api, headers)
    _start_homework(api, headers)

    progress = api.get("/progress/", headers=headers).json()
    assert progress["total_sessions"] == 1
    assert all(r["topic"] != "Homework Help" for r in progress["recent"])


def test_homework_sessions_do_not_appear_in_the_progress_map(api):
    headers = auth_headers(api)
    _start_lesson(api, headers)
    _start_homework(api, headers)

    topics = api.get("/progress/map", headers=headers).json()["topics"]
    assert "Homework Help" not in [t["topic"] for t in topics]


# ---------------------------------------------------------------------------
# Students must be able to get back to a homework session
# ---------------------------------------------------------------------------

def test_homework_sessions_can_be_listed_for_resuming(api):
    headers = auth_headers(api)
    _start_lesson(api, headers)
    homework = _start_homework(api, headers)
    # A real conversation, not just an upload — see the activity-filter test
    # below for the case where the student never actually replies.
    api.post(
        f"/tutor/{homework['id']}/turn",
        json={"content": "I think it's 3/4"},
        headers=headers,
    )

    listed = api.get("/tutor/homework", headers=headers).json()
    assert [s["id"] for s in listed] == [homework["id"]]
    assert listed[0]["mode"] == SessionMode.HOMEWORK.value


def test_homework_session_with_an_uploaded_file_is_listed_without_a_reply(api):
    """An uploaded homework file is historical student data even when the
    student never sent a chat message after analysis."""
    headers = auth_headers(api)
    homework = _start_homework(api, headers)

    listed = api.get("/tutor/homework", headers=headers).json()
    assert [session["id"] for session in listed] == [homework["id"]]


def test_truly_empty_homework_session_is_not_listed(api):
    """A bare click that created neither a file nor a conversation remains
    hidden from resumable homework history."""
    headers = auth_headers(api)
    api.post("/tutor/homework", json={"subject": "math"}, headers=headers)

    assert api.get("/tutor/homework", headers=headers).json() == []


def test_homework_list_is_per_student(api):
    owner = auth_headers(api, email="owner@example.com")
    _start_homework(api, owner)
    other = auth_headers(api, email="other@example.com")
    assert api.get("/tutor/homework", headers=other).json() == []


# ---------------------------------------------------------------------------
# Study materials reach a real lesson conversation
# ---------------------------------------------------------------------------

def test_uploaded_study_material_is_retrievable_in_a_matching_lesson(api, tmp_path):
    """The end-to-end payoff: upload a file, start a lesson on that topic, and
    the retriever surfaces the passage for the tutor."""
    from app.files.retrieval import KeywordMaterialRetriever
    from app.models.student import Student
    from app.repositories.student_repo import StudentRepository

    headers = auth_headers(api)
    api.post(
        "/materials/",
        files={
            "file": (
                "fractions.txt",
                b"To add fractions with the same denominator, add the numerators "
                b"and keep the denominator the same.",
                "text/plain",
            )
        },
        data={"subject": "math", "topic": "Fractions"},
        headers=headers,
    )

    # Query the retriever the way LessonContext does for a chat turn.
    from app.db.database import get_db

    db = next(app.dependency_overrides[get_db]())
    try:
        student: Student = db.query(Student).first()
        hits = KeywordMaterialRetriever().retrieve(
            db,
            student_id=student.id,
            query="how do I add fractions with the same denominator?",
            subject="math",
            topic="Fractions",
        )
        assert hits, "the uploaded material should be retrievable for this lesson"
        assert "numerators" in hits[0].content
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Authorization across every new endpoint
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "method,path",
    [
        ("get", "/materials/"),
        ("post", "/materials/"),
        ("get", "/materials/supported-formats"),
        ("post", "/tutor/homework"),
        ("get", "/tutor/homework"),
    ],
)
def test_new_endpoints_require_authentication(api, method, path):
    assert getattr(api, method)(path).status_code == 401


def test_cannot_read_another_students_homework_files(api):
    owner = auth_headers(api, email="owner@example.com")
    session = _start_homework(api, owner)
    intruder = auth_headers(api, email="intruder@example.com")
    assert (
        api.get(f"/materials/homework/{session['id']}", headers=intruder).status_code
        == 404
    )


def test_cannot_reprocess_another_students_material(api):
    owner = auth_headers(api, email="owner@example.com")
    material = api.post(
        "/materials/",
        files={"file": ("notes.txt", b"Private notes.", "text/plain")},
        headers=owner,
    ).json()
    intruder = auth_headers(api, email="intruder@example.com")
    assert (
        api.post(f"/materials/{material['id']}/reprocess", headers=intruder).status_code
        == 404
    )
