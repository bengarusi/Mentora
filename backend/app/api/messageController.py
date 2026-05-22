from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_student
from app.db.database import get_db
from app.models.student import Student
from app.schemas.message import MessageCreate, MessageResponse
from app.services.message_service import create_message
from app.services.session_service import get_owned_session_or_404

router = APIRouter(prefix="/messages", tags=["messages"])


@router.post("/{session_id}", response_model=MessageResponse, deprecated=True)
def send_message(
    session_id: int,
    data: MessageCreate,
    db: Session = Depends(get_db),
    student: Student = Depends(get_current_student),
):
    """Deprecated debug endpoint. Real lesson turns go through /tutor/{id}/turn."""
    get_owned_session_or_404(db, student.id, session_id)
    return create_message(db, session_id, data.role, data.content)
