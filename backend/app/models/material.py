from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.enums import MaterialKind, MaterialStatus
from app.db.database import Base


class StudyMaterial(Base):
    """A file a student uploaded — either a persistent study resource or the
    homework attached to one Homework Help session.

    The row carries the retrieval metadata (subject / topic / subtopic) and the
    extraction lifecycle (`status`), while the extracted text lives both here
    (`extracted_text`, for whole-document use like homework) and split across
    `chunks` (for targeted retrieval during a lesson)."""

    __tablename__ = "study_materials"

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(
        Integer, ForeignKey("students.id"), nullable=False, index=True
    )
    # Set only for homework files, which belong to exactly one session. Study
    # materials stay null: they outlive any single lesson.
    session_id = Column(
        Integer, ForeignKey("lesson_sessions.id"), nullable=True, index=True
    )
    kind = Column(
        String, nullable=False, default=MaterialKind.STUDY_MATERIAL.value, index=True
    )

    # ---- retrieval metadata: what this file is *about* ----
    subject = Column(String, nullable=True, index=True)   # e.g. "math"
    topic = Column(String, nullable=True, index=True)     # e.g. "Fractions"
    subtopic = Column(String, nullable=True)              # e.g. "Adding fractions"
    title = Column(String, nullable=True)                 # student-facing label

    # ---- the file itself ----
    filename = Column(String, nullable=False)             # original upload name
    content_type = Column(String, nullable=True)          # sniffed / browser-reported MIME
    size_bytes = Column(Integer, nullable=False, default=0)
    storage_key = Column(String, nullable=False)          # opaque key for FileStorage

    # ---- extraction pipeline ----
    status = Column(
        String, nullable=False, default=MaterialStatus.PENDING.value, index=True
    )
    status_detail = Column(Text, nullable=True)   # why it is unsupported / failed
    extracted_text = Column(Text, nullable=True)  # full plain text, once extracted
    page_count = Column(Integer, nullable=True)   # pages / slides, when meaningful

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    processed_at = Column(DateTime(timezone=True), nullable=True)

    chunks = relationship(
        "MaterialChunk",
        back_populates="material",
        cascade="all, delete-orphan",
        order_by="MaterialChunk.chunk_index",
    )


class MaterialChunk(Base):
    """One retrievable slice of a material's text.

    Chunks are what the retriever ranks and what the tutor actually sees, so a
    lesson pulls in only the relevant passages instead of whole documents. The
    `embedding` column is the seam for vector search: today's keyword retriever
    leaves it null, and an embedding-backed retriever can populate and query it
    without any schema change."""

    __tablename__ = "material_chunks"

    id = Column(Integer, primary_key=True, index=True)
    material_id = Column(
        Integer, ForeignKey("study_materials.id"), nullable=False, index=True
    )
    chunk_index = Column(Integer, nullable=False, default=0)  # order within the document
    content = Column(Text, nullable=False)
    char_count = Column(Integer, nullable=False, default=0)
    # Nullable until an embedding provider fills it in. JSON keeps this portable
    # across SQLite (tests) and Postgres (dev/prod) without a pgvector dependency.
    embedding = Column(JSON, nullable=True)
    embedding_model = Column(String, nullable=True)

    material = relationship("StudyMaterial", back_populates="chunks")
