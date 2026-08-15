from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
)
from sqlalchemy.sql import func

from app.db.database import Base


class BoardExplanation(Base):
    """One generated board explanation.

    Only successful generations are stored, so a row here means "a board the
    student can replay". Failures are logged and retried, never persisted.

    A board hangs off exactly one anchor, and which one it is says what the board
    is for:

      lesson_intro / chat  -> message_id, a tutor turn in the transcript
      practice_review      -> question_id, a question already graded

    Both anchor columns are unique, which is what makes replaying free and stops
    a board ever being reused for something it was not drawn for. They are
    nullable because only one applies at a time; SQL allows repeated NULLs in a
    unique index, so the other anchor stays unconstrained.
    """

    __tablename__ = "board_explanations"

    id = Column(Integer, primary_key=True, index=True)
    # Denormalised from the anchor so listing and ownership checks need no join,
    # the same trade agent_trace makes.
    session_id = Column(
        Integer, ForeignKey("lesson_sessions.id"), nullable=False, index=True
    )
    kind = Column(String(16), nullable=False)  # lesson_intro | chat | practice_review
    message_id = Column(
        Integer, ForeignKey("messages.id"), nullable=True, index=True, unique=True
    )
    question_id = Column(
        Integer,
        ForeignKey("assessment_questions.id"),
        nullable=True,
        index=True,
        unique=True,
    )
    # Denormalised so the list endpoint can label affordances without
    # deserialising every board.
    title = Column(String(120), nullable=False)
    content_json = Column(JSON, nullable=False)  # the validated BoardSpec
    model = Column(String(64), nullable=True)    # which model produced it
    duration_ms = Column(Float, nullable=True)   # generation latency
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
