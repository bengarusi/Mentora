from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.database import Base


class Performance(Base):
    __tablename__ = "performance"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(
        Integer, ForeignKey("lesson_sessions.id"), unique=True, nullable=False
    )
    success_level = Column(String, nullable=False)   # SuccessLevel enum value
    score = Column(Integer, nullable=False)           # total correct answers across all sets
    total_questions = Column(Integer, nullable=False, default=3)  # total questions across all sets
    practice_sets = Column(Integer, nullable=False, default=1)    # how many practice sets completed
    summary_text = Column(Text, nullable=True)        # AI final lesson summary
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    session = relationship("LessonSession", back_populates="performance")
