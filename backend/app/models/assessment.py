from sqlalchemy import (
    Boolean,
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


class AssessmentQuestion(Base):
    __tablename__ = "assessment_questions"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(
        Integer, ForeignKey("lesson_sessions.id"), nullable=False, index=True
    )
    set_number = Column(Integer, nullable=False, default=1)  # practice set index (1, 2, 3, ...)
    difficulty = Column(Integer, nullable=False)  # 1, 2, 3 = relative difficulty within set
    # DifficultyLevel the lesson stood at when this question was written, copied
    # here rather than read back from the session: progress is credited per
    # question, so the level it was earned at must not move if the lesson's does.
    level = Column(String, nullable=True)  # easy / medium / hard
    question_text = Column(Text, nullable=False)
    correct_answer = Column(Text, nullable=True)   # expected answer text
    solution_steps = Column(Text, nullable=True)   # step-by-step solution
    explanation = Column(Text, nullable=True)       # why this approach works
    criteria = Column(Text, nullable=True)          # legacy grading rubric (kept for grade_answer compat)
    student_answer = Column(Text, nullable=True)    # filled on submit
    is_correct = Column(Boolean, nullable=True)     # graded by LLM
    feedback = Column(Text, nullable=True)          # per-answer child-friendly feedback
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    session = relationship("LessonSession", back_populates="questions")
