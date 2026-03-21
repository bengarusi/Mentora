from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.student import StudentRegister, StudentLogin, StudentResponse
from app.services.auth_service import create_student, authenticate_student

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=StudentResponse)
def register(student: StudentRegister, db: Session = Depends(get_db)):
    return create_student(db, student)


@router.post("/login", response_model=StudentResponse)
def login(data: StudentLogin, db: Session = Depends(get_db)):
    student = authenticate_student(db, data.email, data.password)

    if not student:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    return student