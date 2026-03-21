from sqlalchemy.orm import Session
from app.models.student import Student
from app.schemas.student import StudentRegister
from app.core.security import hash_password, verify_password

def create_student(db: Session, student_data: StudentRegister) -> Student:
 
    hashed_password = hash_password(student_data.password)

    student = Student(
        full_name=student_data.full_name,
        email=student_data.email,
        password_hash=hashed_password,
        age=student_data.age,
        grade=student_data.grade,
        math_level=student_data.math_level,
        english_level=student_data.english_level
    )

    db.add(student)
    db.commit()
    db.refresh(student)

    return student


def authenticate_student(db: Session, email: str, password: str):
    student = db.query(Student).filter(Student.email == email).first()

    if not student:
        return None

    if not verify_password(password, student.password_hash):
        return None

    return student