from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_student
from app.core.security import create_access_token
from app.db.database import get_db
from app.models.student import Student
from app.schemas.auth import LoginResponse
from app.schemas.student import StudentRegister, StudentResponse
from app.services.auth_service import create_student, authenticate_student

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=StudentResponse)
def register(student: StudentRegister, db: Session = Depends(get_db)):
    return create_student(db, student)


@router.get("/me", response_model=StudentResponse)
def get_current_student_profile(student: Student = Depends(get_current_student)):
    return student


@router.post("/login", response_model=LoginResponse)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    student = authenticate_student(db, form_data.username, form_data.password)
    if not student:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_access_token(student.id)
    return LoginResponse(
        access_token=token,
        student=StudentResponse.model_validate(student),
    )
