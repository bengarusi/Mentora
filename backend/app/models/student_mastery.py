from sqlalchemy import JSON, Column, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.sql import func

from app.db.database import Base


class StudentSkillMastery(Base):
    __tablename__ = "student_skill_mastery"
    __table_args__ = (
        UniqueConstraint(
            "student_id", "subject", "topic", "skill", name="uq_student_skill_mastery"
        ),
    )

    id = Column(Integer, primary_key=True)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False, index=True)
    subject = Column(String, nullable=False)
    topic = Column(String, nullable=False)
    skill = Column(String, nullable=False)
    mastery_estimate = Column(Float, nullable=False, default=0.0)
    attempts = Column(Integer, nullable=False, default=0)
    correct = Column(Integer, nullable=False, default=0)
    open_misconceptions = Column(JSON, nullable=False, default=list)
    last_evidence_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
