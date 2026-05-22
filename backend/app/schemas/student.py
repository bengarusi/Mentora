from pydantic import BaseModel, EmailStr

class StudentRegister(BaseModel):
    full_name: str
    email: EmailStr
    password: str
    age: int
    grade: str
    math_level: str | None = None
    english_level: str | None = None

class StudentLogin(BaseModel):
    email: EmailStr
    password: str

class StudentResponse(BaseModel):
    id: int
    full_name: str
    email: EmailStr
    age: int
    grade: str
    math_level: str | None = None
    english_level: str | None = None

    class Config:
        from_attributes = True