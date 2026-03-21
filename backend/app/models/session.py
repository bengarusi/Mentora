from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.sql import func
from app.db.database import Base

class LessonSession(Base):
    __tablename__ = "lesson_sessions"

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False)
    subject = Column(String, nullable=False)  #Math or English
    topic = Column(String, nullable=False)
    goal_text = Column(String, nullable=False)
    status = Column(String, nullable=False, default="active") # ???
    created_at = Column(DateTime(timezone=True), server_default=func.now()) #To track when the session started
    ended_at = Column(DateTime(timezone=True), nullable=True) #To track when the session ended, useful for analytics and improving the tutoring process