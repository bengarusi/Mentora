from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.database import Base


class AssessmentQuestion(Base):
    __tablename__ = "assessment_questions"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(
        Integer, ForeignKey("lesson_sessions.id"), nullable=False, index=True
    )
    difficulty = Column(Integer, nullable=False)  # 1, 2, 3 = increasing
    question_text = Column(Text, nullable=False)
    criteria = Column(Text, nullable=True)  # grading rubric / expected answer
    student_answer = Column(Text, nullable=True)  # filled on submit
    is_correct = Column(Boolean, nullable=True)  # graded by LLM
    feedback = Column(Text, nullable=True)  # per-answer feedback
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    session = relationship("LessonSession", back_populates="questions")
