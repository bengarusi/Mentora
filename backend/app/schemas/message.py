from datetime import datetime
from pydantic import BaseModel

class MessageCreate(BaseModel):
    role: str
    content: str

class MessageResponse(BaseModel):
    id: int
    session_id: int
    role: str
    content: str
    created_at: datetime | None = None

    class Config:
        from_attributes = True