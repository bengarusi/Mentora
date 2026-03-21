from sqlalchemy.orm import Session
from app.models.message import Message

def create_message(db: Session, session_id: int, role: str, content: str):
    message = Message(
        session_id=session_id,
        role=role,
        content=content
    )

    db.add(message)
    db.commit()
    db.refresh(message)

    return message