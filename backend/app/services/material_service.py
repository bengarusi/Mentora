from __future__ import annotations

import logging

from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.sql import func

from app.core.config import settings
from app.core.enums import MaterialKind, MaterialStatus
from app.files.chunking import chunk_text, normalize_text
from app.files.extraction import (
    ExtractionError,
    ExtractorUnavailable,
    get_extractor,
)
from app.files.retrieval import MaterialRetriever, RetrievedChunk
from app.files.storage import FileStorage, FileStorageError
from app.models.material import StudyMaterial
from app.models.student import Student
from app.repositories.material_repo import MaterialChunkRepository, MaterialRepository
from app.schemas.material import MaterialUpdate

log = logging.getLogger("app.services.material_service")


class MaterialService:
    """Owns the upload → extract → chunk lifecycle and the retrieval read path.

    Mirrors TutorService's shape: it authorizes against the current student,
    drives the file pipeline, persists via repositories, and owns the
    transaction (one commit per request)."""

    def __init__(
        self,
        db: Session,
        student: Student,
        storage: FileStorage,
        retriever: MaterialRetriever,
    ):
        self.db = db
        self.student = student
        self.storage = storage
        self.retriever = retriever
        self.materials = MaterialRepository(db)
        self.chunks = MaterialChunkRepository(db)

    # ---- helpers ----

    def _get_owned_or_404(self, material_id: int) -> StudyMaterial:
        material = self.materials.get_owned(material_id, self.student.id)
        if material is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, detail="Material not found"
            )
        return material

    @staticmethod
    def chunk_count(material: StudyMaterial) -> int:
        return len(material.chunks)

    # ---- upload ----

    def upload_material(
        self,
        *,
        data: bytes,
        filename: str,
        content_type: str | None,
        kind: MaterialKind,
        subject: str | None = None,
        topic: str | None = None,
        subtopic: str | None = None,
        title: str | None = None,
        session_id: int | None = None,
    ) -> StudyMaterial:
        """Store one uploaded file and run it through extraction synchronously.

        Extraction is inline because the student is waiting on the result (a
        homework photo is useless until it is read). The status column is the
        seam for moving this to a background worker later: callers already treat
        anything other than READY as "not usable yet"."""
        if not data:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, "The uploaded file is empty."
            )
        max_bytes = settings.MATERIAL_MAX_UPLOAD_MB * 1024 * 1024
        if len(data) > max_bytes:
            raise HTTPException(
                status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                f"Files must be {settings.MATERIAL_MAX_UPLOAD_MB} MB or smaller.",
            )

        safe_name = (filename or "upload").strip() or "upload"
        try:
            storage_key = self.storage.save(
                data, student_id=self.student.id, filename=safe_name
            )
        except FileStorageError as exc:
            log.error("material storage failed student_id=%s error=%s", self.student.id, exc)
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR, "Could not save the file."
            )

        material = self.materials.add(
            StudyMaterial(
                student_id=self.student.id,
                session_id=session_id,
                kind=kind.value,
                subject=subject,
                topic=topic,
                subtopic=subtopic,
                title=(title or safe_name).strip(),
                filename=safe_name,
                content_type=content_type,
                size_bytes=len(data),
                storage_key=storage_key,
                status=MaterialStatus.PENDING.value,
            )
        )

        self._process(material, data)
        self.db.commit()
        self.db.refresh(material)
        log.info(
            "material uploaded id=%s student_id=%s kind=%s status=%s bytes=%d",
            material.id,
            self.student.id,
            material.kind,
            material.status,
            material.size_bytes,
        )
        return material

    def _process(self, material: StudyMaterial, data: bytes) -> None:
        """Extract text and build chunks, recording the outcome on the row.

        Never raises: a file that cannot be read is still a saved upload the
        student can see, re-tag, or delete — it just isn't retrievable."""
        extractor = get_extractor(material.content_type, material.filename)
        if extractor is None:
            material.status = MaterialStatus.UNSUPPORTED.value
            material.status_detail = "This file type isn't supported yet."
            return

        material.status = MaterialStatus.PROCESSING.value
        try:
            document = extractor.extract(data, material.filename)
        except ExtractorUnavailable as exc:
            # Supported format, environment can't read it yet — park it so a
            # later reprocess (new dependency, OCR enabled) can pick it up.
            material.status = MaterialStatus.UNSUPPORTED.value
            material.status_detail = str(exc)
            log.info(
                "material extraction unavailable id=%s reason=%s", material.id, exc
            )
            return
        except ExtractionError as exc:
            material.status = MaterialStatus.FAILED.value
            material.status_detail = str(exc)
            log.warning("material extraction failed id=%s error=%s", material.id, exc)
            return

        text = normalize_text(document.text)
        if not text:
            material.status = MaterialStatus.FAILED.value
            material.status_detail = "No readable text was found in this file."
            return

        material.extracted_text = text
        material.page_count = document.page_count
        self.chunks.replace_for_material(material.id, chunk_text(text))
        material.status = MaterialStatus.READY.value
        material.status_detail = None
        material.processed_at = func.now()

    def reprocess(self, material_id: int) -> StudyMaterial:
        """Re-run extraction on a stored file — the recovery path for materials
        parked as UNSUPPORTED before a dependency or OCR became available."""
        material = self._get_owned_or_404(material_id)
        try:
            data = self.storage.read(material.storage_key)
        except FileStorageError:
            material.status = MaterialStatus.FAILED.value
            material.status_detail = "The stored file could not be read."
            self.db.commit()
            return material

        self._process(material, data)
        self.db.commit()
        self.db.refresh(material)
        return material

    def get_file(self, material_id: int) -> tuple[bytes, StudyMaterial]:
        """The material's raw uploaded bytes plus its row, for viewing/downloading
        the original file the student uploaded."""
        material = self._get_owned_or_404(material_id)
        try:
            data = self.storage.read(material.storage_key)
        except FileStorageError:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, "The stored file could not be read."
            )
        return data, material

    # ---- reads ----

    def list_study_materials(
        self, *, subject: str | None = None, topic: str | None = None
    ) -> list[StudyMaterial]:
        return self.materials.list_study_materials(
            self.student.id, subject=subject, topic=topic
        )

    def update_material(
        self, material_id: int, data: MaterialUpdate
    ) -> StudyMaterial:
        material = self._get_owned_or_404(material_id)
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(material, field, value)
        self.db.commit()
        self.db.refresh(material)
        return material

    def delete_material(self, material_id: int) -> None:
        material = self._get_owned_or_404(material_id)
        storage_key = material.storage_key
        self.materials.delete(material)  # cascades to chunks
        self.db.commit()
        # Only unlink the bytes once the row is committed, so a storage failure
        # can never leave a row pointing at a deleted file.
        self.storage.delete(storage_key)
        log.info("material deleted id=%s student_id=%s", material_id, self.student.id)

    # ---- retrieval (used by the tutor) ----

    def retrieve_relevant(
        self,
        *,
        query: str,
        subject: str | None = None,
        topic: str | None = None,
        limit: int = 4,
    ) -> list[RetrievedChunk]:
        return self.retriever.retrieve(
            self.db,
            student_id=self.student.id,
            query=query,
            subject=subject,
            topic=topic,
            limit=limit,
        )
