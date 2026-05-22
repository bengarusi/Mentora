from sqlalchemy.orm import Session

from app.models.student import Student
from app.repositories.base import BaseRepository


class StudentRepository(BaseRepository[Student]):
    def __init__(self, db: Session):
        super().__init__(db, Student)

    def get_by_email(self, email: str) -> Student | None:
        return self.db.query(Student).filter(Student.email == email).first()
