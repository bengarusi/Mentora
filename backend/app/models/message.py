from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.sql import func
from app.db.database import Base

class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("lesson_sessions.id"), nullable=False)
    role = Column(String, nullable=False)  # student / tutor (who send the message)
    content = Column(Text, nullable=False)
