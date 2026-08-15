from datetime import datetime, timedelta, timezone

from app.core.enums import (
    LessonPhase,
    MaterialKind,
    MaterialStatus,
    MessageRole,
    SessionMode,
    SessionStatus,
)
from app.models.material import MaterialChunk, StudyMaterial
from app.models.message import Message
from app.models.session import LessonSession
from app.repositories.student_repo import StudentRepository
from tests.conftest import auth_headers


def _student_id(session_factory, email: str) -> int:
    with session_factory() as db:
        student = StudentRepository(db).get_by_email(email)
        assert student is not None
        return student.id


def _historical_lesson(session_factory, student_id: int, *, ordinal: int = 0) -> int:
    created = datetime(2025, 1, 1, tzinfo=timezone.utc) + timedelta(days=ordinal)
    with session_factory() as db:
        lesson = LessonSession(
            student_id=student_id,
            subject="math",
            topic="Fractions",
            subtopic=f"Historical lesson {ordinal}",
            goal_text="Review historical work",
            mode=SessionMode.LESSON.value,
            status=SessionStatus.ENDED.value,
            phase=LessonPhase.COMPLETED.value,
            created_at=created,
            ended_at=created + timedelta(hours=1),
        )
        db.add(lesson)
        db.flush()
        db.add_all(
            [
                Message(
                    session_id=lesson.id,
                    role=MessageRole.TUTOR.value,
                    content="First historical message",
                    created_at=created,
                ),
                Message(
                    session_id=lesson.id,
                    role=MessageRole.STUDENT.value,
                    content="Second historical message",
                    created_at=created + timedelta(minutes=1),
                ),
            ]
        )
        db.commit()
        return lesson.id


def _historical_material(
    session_factory, student_id: int, *, ordinal: int = 0, session_id: int | None = None
) -> int:
    created = datetime(2025, 1, 1, tzinfo=timezone.utc) + timedelta(days=ordinal)
    with session_factory() as db:
        material = StudyMaterial(
            student_id=student_id,
            session_id=session_id,
            kind=MaterialKind.STUDY_MATERIAL.value,
            subject="math",
            topic=None,
            subtopic=None,
            title=None,
            filename=f"historical-{ordinal}.txt",
            content_type="text/plain",
            size_bytes=24,
            storage_key=f"{student_id}/historical-{ordinal}.txt",
            status=MaterialStatus.READY.value,
            extracted_text="Historical fractions notes",
            created_at=created,
            processed_at=created,
        )
        db.add(material)
        db.flush()
        db.add(
            MaterialChunk(
                material_id=material.id,
                chunk_index=0,
                content="Historical fractions notes",
                char_count=26,
            )
        )
        db.commit()
        return material.id


def test_completed_legacy_lesson_without_agent_rows_is_visible_and_openable(
    client, session_factory
):
    headers = auth_headers(client, email="owner@example.com")
    student_id = _student_id(session_factory, "owner@example.com")
    lesson_id = _historical_lesson(session_factory, student_id)

    listed = client.get("/sessions/", headers=headers)
    opened = client.get(f"/sessions/{lesson_id}", headers=headers)
    messages = client.get(f"/sessions/{lesson_id}/messages", headers=headers)

    assert listed.status_code == 200
    assert lesson_id in [row["id"] for row in listed.json()]
    assert opened.status_code == 200
    assert opened.json()["phase"] == LessonPhase.COMPLETED.value
    assert [row["content"] for row in messages.json()] == [
        "First historical message",
        "Second historical message",
    ]


def test_historical_material_with_nullable_metadata_and_old_session_is_visible(
    client, session_factory
):
    headers = auth_headers(client, email="owner@example.com")
    student_id = _student_id(session_factory, "owner@example.com")
    lesson_id = _historical_lesson(session_factory, student_id)
    material_id = _historical_material(
        session_factory, student_id, session_id=lesson_id
    )

    response = client.get("/materials/", headers=headers)

    assert response.status_code == 200
    material = next(row for row in response.json()["materials"] if row["id"] == material_id)
    assert material["filename"] == "historical-0.txt"
    assert material["topic"] is None
    assert material["session_id"] == lesson_id
    assert material["chunk_count"] == 1


def test_historical_data_is_strictly_scoped_to_its_owner(client, session_factory):
    owner = auth_headers(client, email="owner@example.com")
    other = auth_headers(client, email="other@example.com")
    owner_id = _student_id(session_factory, "owner@example.com")
    lesson_id = _historical_lesson(session_factory, owner_id)
    material_id = _historical_material(session_factory, owner_id)

    assert lesson_id in [row["id"] for row in client.get("/sessions/", headers=owner).json()]
    assert material_id in [
        row["id"] for row in client.get("/materials/", headers=owner).json()["materials"]
    ]
    assert client.get(f"/sessions/{lesson_id}", headers=other).status_code == 404
    assert client.get(f"/sessions/{lesson_id}/messages", headers=other).status_code == 404
    assert lesson_id not in [row["id"] for row in client.get("/sessions/", headers=other).json()]
    assert material_id not in [
        row["id"] for row in client.get("/materials/", headers=other).json()["materials"]
    ]


def test_all_history_is_reachable_across_explicit_page_boundaries(
    client, session_factory
):
    headers = auth_headers(client, email="owner@example.com")
    student_id = _student_id(session_factory, "owner@example.com")
    lesson_ids = [_historical_lesson(session_factory, student_id, ordinal=i) for i in range(12)]
    material_ids = [_historical_material(session_factory, student_id, ordinal=i) for i in range(12)]

    lesson_pages = [
        client.get(f"/sessions/?limit=5&offset={offset}", headers=headers).json()
        for offset in (0, 5, 10)
    ]
    material_pages = [
        client.get(f"/materials/?limit=5&offset={offset}", headers=headers).json()["materials"]
        for offset in (0, 5, 10)
    ]

    assert [len(page) for page in lesson_pages] == [5, 5, 2]
    assert [len(page) for page in material_pages] == [5, 5, 2]
    assert {row["id"] for page in lesson_pages for row in page} == set(lesson_ids)
    assert {row["id"] for page in material_pages for row in page} == set(material_ids)
