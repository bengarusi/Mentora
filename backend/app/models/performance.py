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
    success_level = Column(String, nullable=False)  # SuccessLevel enum value
    score = Column(Integer, nullable=False)  # number of correct answers (0..3)
    summary_text = Column(Text, nullable=True)  # AI session summary
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    session = relationship("LessonSession", back_populates="performance")
