from datetime import datetime
from pydantic import BaseModel

from app.core.enums import Subject

class SessionCreate(BaseModel):
    subject: Subject
    topic: str
    goal_text: str

class SessionResponse(BaseModel):
    id: int
    student_id: int
    subject: str
    topic: str
    goal_text: str
    status: str
    phase: str | None = None
    created_at: datetime | None = None
    ended_at: datetime | None = None

    class Config:
        from_attributes = True