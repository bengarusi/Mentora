from sqlalchemy import JSON, Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.enums import LessonPhase, SessionMode, SessionStatus
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
    mode = Column(
        String, nullable=False, default=SessionMode.LESSON.value, index=True
    )  # lesson (teaching→practice ladder) or homework (single-phase help chat)
    status = Column(String, nullable=False, default=SessionStatus.ACTIVE.value)  # lifecycle
    phase = Column(String, nullable=False, default=LessonPhase.TEACHING.value)  # pedagogical phase
    difficulty = Column(String, nullable=True)  # student-chosen easy/medium/hard, set after teaching starts
    homework_outline = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    # When the student last opened this lesson. Lesson history is a list of
    # where they have been, not of what they started, so it is ordered by this
    # rather than by creation: reopening an old lesson brings it back to the top.
    last_opened_at = Column(DateTime(timezone=True), server_default=func.now())
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
    # Homework files attached to this session (empty for normal lessons).
    materials = relationship(
        "StudyMaterial",
        cascade="all, delete-orphan",
    )
