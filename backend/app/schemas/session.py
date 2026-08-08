from datetime import datetime
from pydantic import BaseModel, Field

from app.core.enums import Subject

class SessionCreate(BaseModel):
    subject: Subject
    topic: str
    subtopic: str = Field(min_length=1)  # mandatory precise lesson focus
    goal_text: str

class SessionResponse(BaseModel):
    id: int
    student_id: int
    subject: str
    topic: str
    subtopic: str
    goal_text: str
    status: str
    phase: str | None = None
    difficulty: str | None = None
    created_at: datetime | None = None
    ended_at: datetime | None = None

    class Config:
        from_attributes = True