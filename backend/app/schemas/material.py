from datetime import datetime

from pydantic import BaseModel


class MaterialResponse(BaseModel):
    id: int
    student_id: int
    session_id: int | None = None
    kind: str
    subject: str | None = None
    topic: str | None = None
    subtopic: str | None = None
    title: str | None = None
    filename: str
    content_type: str | None = None
    size_bytes: int
    status: str
    status_detail: str | None = None
    page_count: int | None = None
    chunk_count: int = 0
    created_at: datetime | None = None
    processed_at: datetime | None = None

    class Config:
        from_attributes = True


class MaterialUpdate(BaseModel):
    """Re-filing a material under a different topic. Any omitted field is left
    untouched, so the UI can patch one tag at a time."""

    subject: str | None = None
    topic: str | None = None
    subtopic: str | None = None
    title: str | None = None


class MaterialListResponse(BaseModel):
    materials: list[MaterialResponse]


class SupportedFormatsResponse(BaseModel):
    """Lets the frontend build its file picker from the server's real
    capabilities instead of a hard-coded list that can drift."""

    extensions: list[str]
    max_upload_mb: int


class HomeworkSessionCreate(BaseModel):
    """Homework Help needs no curriculum pick — the uploaded work defines the
    subject matter — so every field is optional with a sensible default."""

    subject: str = "math"
    title: str | None = None
