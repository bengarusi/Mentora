from sqlalchemy import JSON, Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.sql import func

from app.db.database import Base


class AgentTrace(Base):
    __tablename__ = "agent_trace"

    id = Column(Integer, primary_key=True)
    run_id = Column(String(36), nullable=False, index=True)
    session_id = Column(Integer, ForeignKey("lesson_sessions.id"), nullable=False, index=True)
    step = Column(Integer, nullable=False)
    kind = Column(String, nullable=False)
    tool_name = Column(String, nullable=True)
    args_json = Column(JSON, nullable=True)
    result_json = Column(JSON, nullable=True)
    duration_ms = Column(Float, nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
