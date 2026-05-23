from pydantic import BaseModel


class RecentSessionDTO(BaseModel):
    session_id: int
    subject: str
    topic: str
    goal_text: str
    phase: str
    success_level: str | None = None
    score: int | None = None
    total_questions: int | None = None


class StudentProgressResponse(BaseModel):
    total_sessions: int
    completed_sessions: int
    sessions_by_subject: dict[str, int]
    success_distribution: dict[str, int]
    # Overall aggregates across all sessions
    total_correct_answered: int = 0
    total_questions_answered: int = 0
    average_percentage: float | None = None  # 0–100, replaces the old "avg score / 3"
    recent: list[RecentSessionDTO] = []


# ---- topic/subtopic progress map ----
# status is one of: mastered | in_progress | needs_practice | not_started


class SubtopicProgress(BaseModel):
    subtopic: str  # the stored subtopic title (frontend matches it to the curriculum)
    mastery_percentage: int | None = None
    status: str
    sessions_count: int = 0
    last_session_id: int | None = None


class TopicProgress(BaseModel):
    topic: str  # the stored topic title
    mastery_percentage: int | None = None
    status: str
    sessions_count: int = 0
    subtopics: list[SubtopicProgress] = []


class ProgressMapResponse(BaseModel):
    topics: list[TopicProgress] = []
