from sqlalchemy.orm import Session

from app.models.message import Message
from app.repositories.base import BaseRepository


class MessageRepository(BaseRepository[Message]):
    def __init__(self, db: Session):
        super().__init__(db, Message)

    def get_specific_session_messages_history(self, session_id: int) -> list[Message]:
        return (
            self.db.query(Message)
            .filter(Message.session_id == session_id)
            .order_by(Message.created_at.asc(), Message.id.asc())
            .all()
        )

    def get_recent_session_messages(
        self, session_id: int, limit: int
    ) -> list[Message]:
        """Return the last *limit* messages in chronological order, fetched with a
        SQL LIMIT instead of loading the whole history and slicing in Python."""
        rows = (
            self.db.query(Message)
            .filter(Message.session_id == session_id)
            .order_by(Message.created_at.desc(), Message.id.desc())
            .limit(limit)
            .all()
        )
        rows.reverse()
        return rows
