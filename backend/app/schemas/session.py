from pydantic import BaseModel

class SessionCreate(BaseModel):
    student_id: int
    subject: str
    topic: str
    goal_text: str

class SessionResponse(BaseModel):
    id: int
    student_id: int
    subject: str
    topic: str
    goal_text: str
    status: str

    class Config:
        from_attributes = True