"""Deleting a homework session takes everything that hung off it.

Four tables reference a session without an ORM cascade or with one, and a
homework session that ran the agent has rows in most of them, so the delete is
pinned here against every one.
"""

import pytest

from app.api.dependencies import get_storage
from app.files.storage import LocalFileStorage
from app.main import app
from app.models.agent_session_state import AgentSessionState
from app.models.agent_trace import AgentTrace
from app.models.material import StudyMaterial
from app.models.message import Message
from app.models.session import LessonSession
from tests.conftest import auth_headers


@pytest.fixture
def api(client, tmp_path):
    app.dependency_overrides[get_storage] = lambda: LocalFileStorage(tmp_path)
    yield client
    app.dependency_overrides.pop(get_storage, None)


def _homework_with_file(api, headers, text=b"Exercise 1: What is 1/2 + 1/4?"):
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


def test_delete_removes_the_session_and_its_rows(api, db_session):
    headers = auth_headers(api)
    session = _homework_with_file(api, headers)
    sid = session["id"]

    # Something in every table that hangs off a session.
    db_session.add(AgentTrace(session_id=sid, run_id="r", step=0, kind="tool_call"))
    db_session.add(AgentSessionState(session_id=sid, current_goal="", solved_refs=[]))
    db_session.commit()

    assert api.delete(f"/tutor/{sid}/homework", headers=headers).status_code == 204

    assert db_session.query(LessonSession).filter_by(id=sid).count() == 0
    assert db_session.query(Message).filter_by(session_id=sid).count() == 0
    assert db_session.query(StudyMaterial).filter_by(session_id=sid).count() == 0
    assert db_session.query(AgentTrace).filter_by(session_id=sid).count() == 0
    assert db_session.query(AgentSessionState).filter_by(session_id=sid).count() == 0


def test_deleted_homework_leaves_the_listings(api):
    headers = auth_headers(api)
    kept = _homework_with_file(api, headers)
    doomed = _homework_with_file(api, headers)

    api.delete(f"/tutor/{doomed['id']}/homework", headers=headers)

    listed = [s["id"] for s in api.get("/tutor/homework", headers=headers).json()]
    assert listed == [kept["id"]]
    assert api.get(f"/materials/homework/{doomed['id']}", headers=headers).status_code == 404


def test_the_uploaded_file_is_unlinked(api, tmp_path, db_session):
    headers = auth_headers(api)
    session = _homework_with_file(api, headers)
    key = (
        db_session.query(StudyMaterial)
        .filter_by(session_id=session["id"])
        .first()
        .storage_key
    )
    assert (tmp_path / key).exists()

    api.delete(f"/tutor/{session['id']}/homework", headers=headers)

    assert not (tmp_path / key).exists()


def test_a_lesson_cannot_be_deleted_through_this_route(api):
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

    assert api.delete(f"/tutor/{lesson['id']}/homework", headers=headers).status_code == 409
    assert api.get(f"/sessions/{lesson['id']}", headers=headers).status_code == 200


def test_another_student_cannot_delete_your_homework(api):
    headers = auth_headers(api)
    session = _homework_with_file(api, headers)

    other = auth_headers(api, email="other@example.com", password="secret123")
    assert api.delete(f"/tutor/{session['id']}/homework", headers=other).status_code == 404

    listed = [s["id"] for s in api.get("/tutor/homework", headers=headers).json()]
    assert listed == [session["id"]]
