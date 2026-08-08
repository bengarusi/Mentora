from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.enums import LessonPhase, SessionStatus
from app.db.database import Base


class LessonSession(Base):
    __tablename__ = "lesson_sessions"

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(
        Integer, ForeignKey("students.id"), nullable=False, index=True
    )
    subject = Column(String, nullable=False)  # math or english
    topic = Column(String, nullable=False)
    subtopic = Column(String, nullable=False)  # precise lesson focus (mandatory)
    goal_text = Column(String, nullable=False)
    status = Column(String, nullable=False, default=SessionStatus.ACTIVE.value)  # lifecycle
    phase = Column(String, nullable=False, default=LessonPhase.TEACHING.value)  # pedagogical phase
    difficulty = Column(String, nullable=True)  # student-chosen easy/medium/hard, set after teaching starts
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    ended_at = Column(DateTime(timezone=True), nullable=True)

    messages = relationship(
        "Message", back_populates="session", cascade="all, delete-orphan"
    )
    questions = relationship(
        "AssessmentQuestion", back_populates="session", cascade="all, delete-orphan"
    )
    performance = relationship(
        "Performance",
        back_populates="session",
        uselist=False,
        cascade="all, delete-orphan",
    )
