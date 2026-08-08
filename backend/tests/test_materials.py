import pytest

from app.core.enums import MaterialKind, MaterialStatus
from app.files.chunking import chunk_text, normalize_text
from app.files.retrieval import KeywordMaterialRetriever
from app.files.storage import FileStorageError, LocalFileStorage
from app.services.material_service import MaterialService
from tests.conftest import make_student


@pytest.fixture
def storage(tmp_path):
    return LocalFileStorage(tmp_path)


@pytest.fixture
def service(db_session, storage):
    student = make_student(db_session)
    return (
        MaterialService(db_session, student, storage, KeywordMaterialRetriever()),
        student,
    )


def _upload(service, text: str, *, filename="notes.txt", **kwargs):
    return service.upload_material(
        data=text.encode("utf-8"),
        filename=filename,
        content_type="text/plain",
        kind=kwargs.pop("kind", MaterialKind.STUDY_MATERIAL),
        **kwargs,
    )


# ---- storage ----

def test_storage_roundtrip_and_delete(storage):
    key = storage.save(b"hello", student_id=7, filename="a.txt")
    assert key.startswith("7/")
    assert storage.read(key) == b"hello"
    storage.delete(key)
    with pytest.raises(FileStorageError):
        storage.read(key)


def test_storage_rejects_key_escaping_the_root(storage):
    with pytest.raises(FileStorageError):
        storage.read("../../etc/passwd")


# ---- chunking ----

def test_chunk_text_splits_on_paragraphs_and_overlaps():
    para = "Fractions are parts of a whole. " * 20  # comfortably over one chunk
    chunks = chunk_text(f"{para}\n\n{para}", chunk_chars=300, overlap_chars=50)
    assert len(chunks) > 1
    assert all(c.strip() for c in chunks)


def test_chunk_text_handles_empty_and_normalizes_whitespace():
    assert chunk_text("   \n\n  ") == []
    assert normalize_text("a  \r\n\r\n\r\n b") == "a\n\nb"


# ---- upload + extraction ----

def test_upload_plain_text_becomes_ready_and_chunked(service):
    svc, _ = service
    material = _upload(svc, "Adding fractions means adding the numerators.")
    assert material.status == MaterialStatus.READY.value
    assert material.extracted_text
    assert MaterialService.chunk_count(material) >= 1


def test_upload_unsupported_type_is_parked_not_failed(service):
    svc, _ = service
    material = svc.upload_material(
        data=b"\x00\x01binary",
        filename="mystery.bin",
        content_type="application/octet-stream",
        kind=MaterialKind.STUDY_MATERIAL,
    )
    assert material.status == MaterialStatus.UNSUPPORTED.value
    assert material.status_detail


def test_upload_rejects_empty_file(service):
    svc, _ = service
    with pytest.raises(Exception) as exc:
        _upload(svc, "")
    assert "422" in str(exc.value) or "empty" in str(exc.value).lower()


def test_reprocess_is_idempotent_and_does_not_duplicate_chunks(service):
    svc, _ = service
    material = _upload(svc, "Place value tells you what each digit is worth.")
    before = MaterialService.chunk_count(material)
    again = svc.reprocess(material.id)
    assert again.status == MaterialStatus.READY.value
    assert MaterialService.chunk_count(again) == before


# ---- listing / update / delete ----

def test_list_filters_by_subject_and_excludes_homework(service):
    svc, _ = service
    _upload(svc, "Math notes about fractions.", subject="math", topic="Fractions")
    _upload(svc, "English notes.", filename="eng.txt", subject="english")
    _upload(svc, "My homework sheet.", filename="hw.txt", kind=MaterialKind.HOMEWORK)

    assert len(svc.list_study_materials()) == 2  # homework excluded
    math_only = svc.list_study_materials(subject="math")
    assert [m.subject for m in math_only] == ["math"]


def test_delete_removes_row_and_stored_bytes(service, storage):
    svc, _ = service
    material = _upload(svc, "Temporary notes.")
    key = material.storage_key
    svc.delete_material(material.id)
    assert svc.list_study_materials() == []
    with pytest.raises(FileStorageError):
        storage.read(key)


def test_cannot_touch_another_students_material(db_session, storage):
    owner = make_student(db_session, email="owner@example.com")
    intruder = make_student(db_session, email="intruder@example.com")
    owner_svc = MaterialService(db_session, owner, storage, KeywordMaterialRetriever())
    material = _upload(owner_svc, "Private notes.")

    intruder_svc = MaterialService(
        db_session, intruder, storage, KeywordMaterialRetriever()
    )
    with pytest.raises(Exception) as exc:
        intruder_svc.delete_material(material.id)
    assert "404" in str(exc.value) or "not found" in str(exc.value).lower()


# ---- retrieval ----

def test_retrieval_returns_only_relevant_material(service):
    svc, _ = service
    _upload(
        svc,
        "Equivalent fractions have the same value. Multiply the numerator and "
        "denominator by the same number.",
        filename="fractions.txt",
        subject="math",
        topic="Fractions",
    )
    _upload(
        svc,
        "A perimeter is the total distance around the outside of a shape.",
        filename="perimeter.txt",
        subject="math",
        topic="Geometry",
    )

    hits = svc.retrieve_relevant(query="how do equivalent fractions work?", subject="math")
    assert hits, "expected the fractions material to match"
    assert "fractions" in hits[0].material_title


def test_retrieval_returns_nothing_for_unrelated_query(service):
    svc, _ = service
    _upload(svc, "A perimeter is the distance around a shape.", subject="math")
    assert svc.retrieve_relevant(query="photosynthesis in plants", subject="math") == []


def test_retrieval_ignores_materials_that_are_not_ready(service):
    svc, _ = service
    svc.upload_material(
        data=b"\x00binary",
        filename="unreadable.bin",
        content_type="application/octet-stream",
        kind=MaterialKind.STUDY_MATERIAL,
        subject="math",
    )
    assert svc.retrieve_relevant(query="binary unreadable", subject="math") == []


def test_retrieval_excludes_homework_from_lesson_context(service):
    svc, _ = service
    _upload(
        svc,
        "Homework: solve 3/4 plus 1/4 and show your work on fractions.",
        filename="hw.txt",
        kind=MaterialKind.HOMEWORK,
        subject="math",
    )
    assert svc.retrieve_relevant(query="fractions homework", subject="math") == []
