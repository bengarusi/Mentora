from sqlalchemy.orm import Session

from app.models.message import Message
from app.repositories.message_repo import MessageRepository


def create_message(
    db: Session, session_id: int, role: str, content: str
) -> Message:
    repo = MessageRepository(db)
    message = Message(session_id=session_id, role=role, content=content)
    repo.add(message)
    db.commit()
    db.refresh(message)
    return message
