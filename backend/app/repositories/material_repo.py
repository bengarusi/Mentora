from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.enums import MaterialKind
from app.models.material import MaterialChunk, StudyMaterial
from app.repositories.base import BaseRepository


class MaterialRepository(BaseRepository[StudyMaterial]):
    def __init__(self, db: Session):
        super().__init__(db, StudyMaterial)

    def get_owned(self, material_id: int, student_id: int) -> StudyMaterial | None:
        return (
            self.db.query(StudyMaterial)
            .filter(
                StudyMaterial.id == material_id,
                StudyMaterial.student_id == student_id,
            )
            .first()
        )

    def list_study_materials(
        self, student_id: int, *, subject: str | None = None, topic: str | None = None
    ) -> list[StudyMaterial]:
        query = self.db.query(StudyMaterial).filter(
            StudyMaterial.student_id == student_id,
            StudyMaterial.kind == MaterialKind.STUDY_MATERIAL.value,
        )
        if subject:
            query = query.filter(StudyMaterial.subject == subject)
        if topic:
            query = query.filter(StudyMaterial.topic == topic)
        return query.order_by(StudyMaterial.created_at.desc()).all()

    def chunk_counts_for(self, material_ids: list[int]) -> dict[int, int]:
        """Chunk counts for many materials in one query.

        Listing endpoints use this instead of `len(material.chunks)` per row,
        which would lazy-load every chunk's full text just to count them."""
        if not material_ids:
            return {}
        rows = (
            self.db.query(MaterialChunk.material_id, func.count(MaterialChunk.id))
            .filter(MaterialChunk.material_id.in_(material_ids))
            .group_by(MaterialChunk.material_id)
            .all()
        )
        counts = dict(rows)
        return {mid: counts.get(mid, 0) for mid in material_ids}

    def list_session_materials(self, session_id: int) -> list[StudyMaterial]:
        """Homework files attached to one Homework Help session, oldest first
        so the tutor sees them in upload order."""
        return (
            self.db.query(StudyMaterial)
            .filter(StudyMaterial.session_id == session_id)
            .order_by(StudyMaterial.created_at.asc())
            .all()
        )


class MaterialChunkRepository(BaseRepository[MaterialChunk]):
    def __init__(self, db: Session):
        super().__init__(db, MaterialChunk)

    def replace_for_material(
        self, material_id: int, contents: list[str]
    ) -> list[MaterialChunk]:
        """Swap in a fresh set of chunks, so re-processing a material is
        idempotent instead of accumulating stale duplicates."""
        # Deleted through the ORM (not a bulk DELETE) so the identity map and
        # the material's loaded `chunks` collection stay consistent afterwards.
        for stale in (
            self.db.query(MaterialChunk)
            .filter(MaterialChunk.material_id == material_id)
            .all()
        ):
            self.db.delete(stale)
        self.db.flush()

        rows = [
            MaterialChunk(
                material_id=material_id,
                chunk_index=index,
                content=content,
                char_count=len(content),
            )
            for index, content in enumerate(contents)
        ]
        self.db.add_all(rows)
        self.db.flush()
        return rows
