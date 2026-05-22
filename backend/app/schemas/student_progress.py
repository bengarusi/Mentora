from pydantic import BaseModel


class RecentSessionDTO(BaseModel):
    session_id: int
    subject: str
    topic: str
    goal_text: str
    phase: str
    success_level: str | None = None
    score: int | None = None


class StudentProgressResponse(BaseModel):
    total_sessions: int
    completed_sessions: int
    sessions_by_subject: dict[str, int]
    success_distribution: dict[str, int]
    average_score: float | None = None
    recent: list[RecentSessionDTO] = []
