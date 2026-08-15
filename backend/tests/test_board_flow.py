"""End-to-end journey for visual board explanations over HTTP.

Walks the sequence the feature is specified by: the lesson opens on the board,
the student asks for another one mid-lesson, both replay without regenerating,
and a practice question stays board-free until it has been graded.
"""

import json

import pytest

from app.core.config import settings
from tests.conftest import auth_headers


@pytest.fixture(autouse=True)
def board_enabled(monkeypatch):
    monkeypatch.setattr(settings, "BOARD_EXPLANATION_ENABLED", True)


def _start_lesson(client, headers) -> int:
    session = client.post(
        "/sessions/",
        json={
            "subject": "math",
            "topic": "Numbers & Place Value",
            "subtopic": "Comparing numbers",
            "goal_text": "I want to compare numbers using <, >, and =.",
        },
        headers=headers,
    ).json()
    sid = session["id"]
    client.post(f"/tutor/{sid}/difficulty", json={"level": "easy"}, headers=headers)
    return sid


def _reach_practice(client, headers, sid) -> list[dict]:
    client.post(f"/tutor/{sid}/advance", headers=headers)  # teaching -> pre-practice
    started = client.post(f"/tutor/{sid}/practice/start", headers=headers)
    assert started.status_code == 200, started.text
    return started.json()["questions"]


# ---- the lesson journey ----------------------------------------------------

def test_the_lesson_opens_on_the_board_and_replays_without_regenerating(client):
    headers = auth_headers(client)
    sid = _start_lesson(client, headers)

    # Nothing exists until the lesson is opened on the board.
    listing = client.get(f"/tutor/{sid}/boards", headers=headers).json()
    assert listing == {"enabled": True, "boards": []}

    opened = client.post(f"/tutor/{sid}/boards/lesson", headers=headers)
    assert opened.status_code == 201, opened.text
    board = opened.json()
    assert board["kind"] == "lesson_intro"
    assert board["message_id"] is not None
    assert board["spec"]["blocks"], "a board must carry something to render"
    assert all(block["narration"] for block in board["spec"]["blocks"])

    # The opening turn is in the transcript, so the board has a place in the chat.
    messages = client.get(f"/sessions/{sid}/messages", headers=headers).json()
    assert any(m["id"] == board["message_id"] for m in messages)

    # Opening again replays rather than redrawing.
    again = client.post(f"/tutor/{sid}/boards/lesson", headers=headers)
    assert again.status_code == 200, "the lesson opening must not be regenerated"
    assert again.json()["id"] == board["id"]

    # And it can be fetched by id after a refresh.
    reopened = client.get(f"/tutor/{sid}/boards/{board['id']}", headers=headers)
    assert reopened.status_code == 200
    assert reopened.json()["spec"] == board["spec"]


def test_a_mid_lesson_request_draws_a_new_board_about_what_was_asked(client):
    headers = auth_headers(client)
    sid = _start_lesson(client, headers)
    intro = client.post(f"/tutor/{sid}/boards/lesson", headers=headers).json()

    asked = client.post(
        f"/tutor/{sid}/boards/lesson",
        json={"focus": "why does the open mouth eat the bigger number"},
        headers=headers,
    )

    assert asked.status_code == 201
    assert asked.json()["id"] != intro["id"]
    assert asked.json()["kind"] == "chat"
    listing = client.get(f"/tutor/{sid}/boards", headers=headers).json()
    assert [b["kind"] for b in listing["boards"]] == ["lesson_intro", "chat"]


def test_the_board_can_be_spoken_block_by_block(client):
    headers = auth_headers(client)
    sid = _start_lesson(client, headers)
    board = client.post(f"/tutor/{sid}/boards/lesson", headers=headers).json()

    response = client.post(f"/tutor/{sid}/boards/{board['id']}/narration", headers=headers)

    assert response.status_code == 200
    events = [json.loads(line) for line in response.text.splitlines() if line]
    types = [event["type"] for event in events]
    assert types[-1] == "done"
    # One audio chunk per block, in order, so the player can reveal block N when
    # chunk N starts.
    starts = [e["chunk_id"] for e in events if e["type"] == "audio_start"]
    assert starts == list(range(len(board["spec"]["blocks"])))


# ---- practice ---------------------------------------------------------------

def test_a_question_being_answered_has_no_board(client):
    """The student works practice out alone; the board only helps afterwards."""
    headers = auth_headers(client)
    sid = _start_lesson(client, headers)
    questions = _reach_practice(client, headers, sid)

    refused = client.post(
        f"/tutor/{sid}/practice/questions/{questions[0]['id']}/board", headers=headers
    )

    assert refused.status_code == 409
    assert client.get(f"/tutor/{sid}/boards", headers=headers).json()["boards"] == []


def test_a_graded_question_can_be_reviewed_and_replayed(client):
    headers = auth_headers(client)
    sid = _start_lesson(client, headers)
    questions = _reach_practice(client, headers, sid)
    client.post(
        f"/tutor/{sid}/practice/submit",
        json={"answers": [{"question_id": q["id"], "answer": "correct1"} for q in questions]},
        headers=headers,
    )

    created = client.post(
        f"/tutor/{sid}/practice/questions/{questions[0]['id']}/board", headers=headers
    )
    again = client.post(
        f"/tutor/{sid}/practice/questions/{questions[0]['id']}/board", headers=headers
    )

    assert created.status_code == 201
    assert created.json()["kind"] == "practice_review"
    assert again.status_code == 200
    assert again.json()["id"] == created.json()["id"]


def test_a_new_practice_set_starts_with_no_boards(client):
    """Practice More mints new question rows, so no board can carry over."""
    headers = auth_headers(client)
    sid = _start_lesson(client, headers)
    questions = _reach_practice(client, headers, sid)
    client.post(
        f"/tutor/{sid}/practice/submit",
        json={"answers": [{"question_id": q["id"], "answer": "correct1"} for q in questions]},
        headers=headers,
    )
    client.post(f"/tutor/{sid}/practice/questions/{questions[0]['id']}/board", headers=headers)

    next_set = client.post(f"/tutor/{sid}/practice/next", headers=headers).json()
    listing = client.get(f"/tutor/{sid}/boards", headers=headers).json()

    new_ids = {q["id"] for q in next_set["questions"]}
    assert new_ids.isdisjoint({b["question_id"] for b in listing["boards"]})


def test_board_failure_leaves_the_lesson_fully_usable(client, monkeypatch):
    """A board that cannot be drawn must not break the chat or the transcript."""
    from app.llm.provider import LLMError
    from tests.fake_llm import FakeLLMProvider

    headers = auth_headers(client)
    sid = _start_lesson(client, headers)

    def explode(self, system, user):
        raise LLMError("upstream is down")

    monkeypatch.setattr(FakeLLMProvider, "generate_board_explanation", explode)
    failed = client.post(f"/tutor/{sid}/boards/lesson", headers=headers)
    turn = client.post(
        f"/tutor/{sid}/turn", json={"content": "can you explain again?"}, headers=headers
    )

    assert failed.status_code == 502
    assert turn.status_code == 200, "chat must be unaffected by a board failure"
    messages = client.get(f"/sessions/{sid}/messages", headers=headers).json()
    assert all(m["content"] for m in messages), "no empty turn left behind"


# ---- scoping and access ----------------------------------------------------

def test_a_board_id_from_another_session_does_not_resolve(client):
    headers = auth_headers(client)
    sid_a = _start_lesson(client, headers)
    sid_b = _start_lesson(client, headers)
    board = client.post(f"/tutor/{sid_a}/boards/lesson", headers=headers).json()

    leaked = client.get(f"/tutor/{sid_b}/boards/{board['id']}", headers=headers)

    assert leaked.status_code == 404


def test_another_students_boards_are_not_reachable(client):
    owner = auth_headers(client)
    sid = _start_lesson(client, owner)
    board = client.post(f"/tutor/{sid}/boards/lesson", headers=owner).json()
    intruder = auth_headers(client, email="intruder@example.com")

    assert client.get(f"/tutor/{sid}/boards", headers=intruder).status_code == 404
    assert client.get(f"/tutor/{sid}/boards/{board['id']}", headers=intruder).status_code == 404
    assert client.post(f"/tutor/{sid}/boards/lesson", headers=intruder).status_code == 404


@pytest.mark.parametrize(
    "method,path",
    [
        ("get", "/tutor/1/boards"),
        ("post", "/tutor/1/boards/lesson"),
        ("get", "/tutor/1/boards/1"),
        ("post", "/tutor/1/boards/1/narration"),
        ("post", "/tutor/1/practice/questions/1/board"),
    ],
)
def test_board_endpoints_require_authentication(client, method, path):
    assert getattr(client, method)(path).status_code == 401


# ---- feature flag ----------------------------------------------------------

def test_listing_reports_enabled_false_instead_of_404_when_the_flag_is_off(
    client, monkeypatch
):
    headers = auth_headers(client)
    sid = _start_lesson(client, headers)
    monkeypatch.setattr(settings, "BOARD_EXPLANATION_ENABLED", False)

    response = client.get(f"/tutor/{sid}/boards", headers=headers)

    assert response.status_code == 200, "the frontend must tell disabled from broken"
    assert response.json() == {"enabled": False, "boards": []}


def test_generate_and_fetch_are_absent_when_the_flag_is_off(client, monkeypatch):
    headers = auth_headers(client)
    sid = _start_lesson(client, headers)
    board = client.post(f"/tutor/{sid}/boards/lesson", headers=headers).json()
    monkeypatch.setattr(settings, "BOARD_EXPLANATION_ENABLED", False)

    assert client.post(f"/tutor/{sid}/boards/lesson", headers=headers).status_code == 404
    assert client.get(f"/tutor/{sid}/boards/{board['id']}", headers=headers).status_code == 404
