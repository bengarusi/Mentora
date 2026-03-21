from pydantic import BaseModel

class MessageCreate(BaseModel):
    role: str
    content: str

class MessageResponse(BaseModel):
    id: int
    session_id: int
    role: str
    content: str

    class Config:
        from_attributes = True