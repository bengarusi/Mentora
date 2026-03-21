from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.session import SessionCreate, SessionResponse
from app.services.session_service import create_session, end_session

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("/", response_model=SessionResponse)
def create_new_session(data: SessionCreate, db: Session = Depends(get_db)):
    return create_session(db, data)

router.post("/{session_id}/end")
def end_existing_session(session_id: int, db: Session = Depends(get_db)):
    return end_session(db, session_id)