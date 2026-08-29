from sqlalchemy import JSON, Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.sql import func

from app.db.database import Base


class AgentSessionState(Base):
    __tablename__ = "agent_session_state"

    id = Column(Integer, primary_key=True)
    session_id = Column(
        Integer, ForeignKey("lesson_sessions.id"), nullable=False, unique=True
    )
    current_goal = Column(Text, nullable=False, default="")
    current_exercise_index = Column(Integer, nullable=False, default=1)
    awaiting_response = Column(Boolean, nullable=False, default=False)
    response_target = Column(JSON, nullable=True)
    hint_level = Column(Integer, nullable=False, default=0)
    solved_refs = Column(JSON, nullable=False, default=list)
    skipped_refs = Column(JSON, nullable=False, default=list)
    annotations = Column(JSON, nullable=False, default=list)
    materials_used = Column(JSON, nullable=False, default=list)
    recent_evaluations = Column(JSON, nullable=False, default=list)
    recommended_next_action = Column(String, nullable=False, default="")
    applied_evaluation_keys = Column(JSON, nullable=False, default=list)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
