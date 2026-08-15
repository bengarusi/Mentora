from sqlalchemy.orm import Session

from app.models.board_explanation import BoardExplanation
from app.repositories.base import BaseRepository


class BoardExplanationRepository(BaseRepository[BoardExplanation]):
    def __init__(self, db: Session):
        super().__init__(db, BoardExplanation)

    def get_for_message(self, message_id: int) -> BoardExplanation | None:
        """The board attached to one tutor turn, if it has one."""
        return (
            self.db.query(BoardExplanation)
            .filter(BoardExplanation.message_id == message_id)
            .one_or_none()
        )

    def get_for_question(self, question_id: int) -> BoardExplanation | None:
        """The review board for one graded question, if it has one."""
        return (
            self.db.query(BoardExplanation)
            .filter(BoardExplanation.question_id == question_id)
            .one_or_none()
        )

    def get_owned(self, board_id: int, session_id: int) -> BoardExplanation | None:
        """Scoped fetch — a board id from another session must not resolve."""
        return (
            self.db.query(BoardExplanation)
            .filter(
                BoardExplanation.id == board_id,
                BoardExplanation.session_id == session_id,
            )
            .one_or_none()
        )

    def list_for_session(self, session_id: int) -> list[BoardExplanation]:
        return (
            self.db.query(BoardExplanation)
            .filter(BoardExplanation.session_id == session_id)
            .order_by(BoardExplanation.id.asc())
            .all()
        )
