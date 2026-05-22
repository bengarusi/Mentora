from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password
from app.models.student import Student
from app.repositories.student_repo import StudentRepository
from app.schemas.student import StudentRegister


def create_student(db: Session, student_data: StudentRegister) -> Student:
    repo = StudentRepository(db)

    if repo.get_by_email(student_data.email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    student = Student(
        full_name=student_data.full_name,
        email=student_data.email,
        password_hash=hash_password(student_data.password),
        age=student_data.age,
        grade=student_data.grade,
        math_level=student_data.math_level,
        english_level=student_data.english_level,
    )

    repo.add(student)
    db.commit()
    db.refresh(student)
    return student


def authenticate_student(db: Session, email: str, password: str) -> Student | None:
    repo = StudentRepository(db)
    student = repo.get_by_email(email)
    if not student:
        return None
    if not verify_password(password, student.password_hash):
        return None
    return student
