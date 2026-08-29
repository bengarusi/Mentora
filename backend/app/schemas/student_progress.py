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
# status is one of: mastered | in_progress | not_started. Progress only ever
# climbs, so there is no failing band; "not_started" is the frontend's to assign,
# since a subtopic with no session at all never reaches this response.


class SubtopicProgress(BaseModel):
    subtopic: str  # the stored subtopic title (frontend matches it to the curriculum)
    #: Percent earned from correct practice answers (1/3/5 by level), capped at 100.
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
