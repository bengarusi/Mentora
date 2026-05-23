from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_student
from app.db.database import get_db
from app.models.student import Student
from app.schemas.student_progress import ProgressMapResponse, StudentProgressResponse
from app.services.progress_service import get_progress_map, get_student_progress

router = APIRouter(prefix="/progress", tags=["progress"])


@router.get("/", response_model=StudentProgressResponse)
def get_my_progress(
    db: Session = Depends(get_db),
    student: Student = Depends(get_current_student),
):
    return get_student_progress(db, student.id)


@router.get("/map", response_model=ProgressMapResponse)
def get_my_progress_map(
    db: Session = Depends(get_db),
    student: Student = Depends(get_current_student),
):
    return get_progress_map(db, student.id)
