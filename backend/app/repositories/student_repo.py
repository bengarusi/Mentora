from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.student import Student
from app.repositories.base import BaseRepository


class StudentRepository(BaseRepository[Student]):
    def __init__(self, db: Session):
        super().__init__(db, Student)

    def get_by_email(self, email: str) -> Student | None:
        normalized = email.strip().lower()
        return (
            self.db.query(Student)
            .filter(func.lower(func.trim(Student.email)) == normalized)
            .first()
        )
