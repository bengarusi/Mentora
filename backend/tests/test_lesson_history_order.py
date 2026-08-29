"""Lesson history is a record of where the student has been.

It is ordered by when each lesson was last opened, not by when it was created,
so reopening an old lesson brings it back to the top of the list — which is what
makes the paged history on the progress page land the way a student expects.
"""

import pytest

from app.main import app
from tests.conftest import auth_headers


@pytest.fixture
def api(client):
    yield client
    app.dependency_overrides.pop(None, None)


def _start_lesson(api, headers, subtopic):
    return api.post(
        "/sessions/",
        json={
            "subject": "math",
            "topic": "Fractions",
            "subtopic": subtopic,
            "goal_text": f"Learn {subtopic}",
        },
        headers=headers,
    ).json()


def _listed_ids(api, headers) -> list[int]:
    return [s["id"] for s in api.get("/sessions/", headers=headers).json()]


def test_new_lessons_come_first(api):
    headers = auth_headers(api)
    first = _start_lesson(api, headers, "Adding fractions")
    second = _start_lesson(api, headers, "Comparing fractions")

    assert _listed_ids(api, headers) == [second["id"], first["id"]]


def test_opening_an_older_lesson_moves_it_to_the_top(api):
    headers = auth_headers(api)
    first = _start_lesson(api, headers, "Adding fractions")
    _start_lesson(api, headers, "Comparing fractions")
    third = _start_lesson(api, headers, "Simplifying fractions")

    api.get(f"/sessions/{first['id']}", headers=headers)  # the student goes back

    listed = _listed_ids(api, headers)
    assert listed[0] == first["id"]
    assert listed[1] == third["id"]


def test_reopening_the_newest_lesson_leaves_the_order_alone(api):
    headers = auth_headers(api)
    first = _start_lesson(api, headers, "Adding fractions")
    second = _start_lesson(api, headers, "Comparing fractions")

    api.get(f"/sessions/{second['id']}", headers=headers)

    assert _listed_ids(api, headers) == [second["id"], first["id"]]


def test_another_students_visit_does_not_reorder_your_history(api):
    headers = auth_headers(api)
    first = _start_lesson(api, headers, "Adding fractions")
    second = _start_lesson(api, headers, "Comparing fractions")

    other = auth_headers(api, email="other@example.com", password="secret123")
    api.get(f"/sessions/{first['id']}", headers=other)  # 404 — not theirs

    assert _listed_ids(api, headers) == [second["id"], first["id"]]


def test_every_lesson_carries_its_score_however_old(api):
    """The history pages back through all of them, so none may lose its badge."""
    headers = auth_headers(api)
    ids = [_start_lesson(api, headers, f"Subtopic {n}")["id"] for n in range(12)]

    reported = {
        row["session_id"] for row in api.get("/progress/", headers=headers).json()["recent"]
    }
    assert reported == set(ids)
