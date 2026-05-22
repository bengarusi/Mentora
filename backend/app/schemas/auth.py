from pydantic import BaseModel

from app.schemas.student import StudentResponse


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class LoginResponse(Token):
    student: StudentResponse
