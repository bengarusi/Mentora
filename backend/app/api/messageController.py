from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.message import MessageCreate, MessageResponse
from app.services.message_service import create_message

router = APIRouter(prefix="/messages", tags=["messages"])


@router.post("/{session_id}", response_model=MessageResponse)
def send_message(session_id: int, data: MessageCreate, db: Session = Depends(get_db)):
    return create_message(db, session_id, data.role, data.content)