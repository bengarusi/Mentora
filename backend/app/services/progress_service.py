from sqlalchemy.orm import Session

from app.core.enums import LessonPhase, SuccessLevel
from app.repositories.performance_repo import PerformanceRepository
from app.repositories.session_repo import SessionRepository
from app.schemas.student_progress import (
    ProgressMapResponse,
    RecentSessionDTO,
    StudentProgressResponse,
    SubtopicProgress,
    TopicProgress,
)

_RECENT_LIMIT = 10


def get_student_progress(db: Session, student_id: int) -> StudentProgressResponse:
    sessions = SessionRepository(db).get_lesson_list_for_student(student_id)
    perf_repo = PerformanceRepository(db)

    sessions_by_subject: dict[str, int] = {}
    success_distribution: dict[str, int] = {
        SuccessLevel.ACHIEVED.value: 0,
        SuccessLevel.PARTIALLY.value: 0,
        SuccessLevel.NOT_ACHIEVED.value: 0,
    }
    total_correct = 0
    total_questions = 0
    recent: list[RecentSessionDTO] = []

    for index, session in enumerate(sessions):
        sessions_by_subject[session.subject] = (
            sessions_by_subject.get(session.subject, 0) + 1
        )
        perf = perf_repo.get_specific_session_performance(session.id)
        if perf:
            success_distribution[perf.success_level] = (
                success_distribution.get(perf.success_level, 0) + 1
            )
            total_correct += perf.score or 0
            total_questions += perf.total_questions or 0
        if index < _RECENT_LIMIT:
            recent.append(
                RecentSessionDTO(
                    session_id=session.id,
                    subject=session.subject,
                    topic=session.topic,
                    goal_text=session.goal_text,
                    phase=session.phase,
                    success_level=perf.success_level if perf else None,
                    score=perf.score if perf else None,
                    total_questions=perf.total_questions if perf else None,
                )
            )

    completed = sum(
        1 for s in sessions if s.phase == LessonPhase.COMPLETED.value
    )
    average_percentage = (
        round(100 * total_correct / total_questions, 1)
        if total_questions > 0
        else None
    )

    return StudentProgressResponse(
        total_sessions=len(sessions),
        completed_sessions=completed,
        sessions_by_subject=sessions_by_subject,
        success_distribution=success_distribution,
        total_correct_answered=total_correct,
        total_questions_answered=total_questions,
        average_percentage=average_percentage,
        recent=recent,
    )


def _status_from_pct(
    pct: int | None, *, has_sessions: bool, has_questions: bool
) -> str:
    if not has_sessions:
        return "not_started"
    if not has_questions or pct is None:
        return "in_progress"
    if pct >= 80:
        return "mastered"
    if pct >= 50:
        return "in_progress"
    return "needs_practice"


def get_progress_map(db: Session, student_id: int) -> ProgressMapResponse:
    """Group the student's sessions by (topic, subtopic) and compute mastery %.

    Sessions come back newest-first, so the first one seen per subtopic is the
    most recent (used for `last_session_id`). The frontend overlays this onto the
    full curriculum so not-started topics still appear."""
    sessions = SessionRepository(db).get_lesson_list_for_student(student_id)
    perf_repo = PerformanceRepository(db)

    # topic_title -> subtopic_title -> aggregate
    topic_map: dict[str, dict[str, dict]] = {}
    for s in sessions:
        subtopic_title = (getattr(s, "subtopic", None) or "General").strip() or "General"
        subs = topic_map.setdefault(s.topic, {})
        agg = subs.setdefault(
            subtopic_title,
            {"correct": 0, "questions": 0, "sessions": 0, "last_session_id": None},
        )
        agg["sessions"] += 1
        if agg["last_session_id"] is None:
            agg["last_session_id"] = s.id
        perf = perf_repo.get_specific_session_performance(s.id)
        if perf:
            agg["correct"] += perf.score or 0
            agg["questions"] += perf.total_questions or 0

    topics: list[TopicProgress] = []
    for topic_title, subs in topic_map.items():
        sub_list: list[SubtopicProgress] = []
        t_correct = t_questions = t_sessions = 0
        for subtopic_title, agg in subs.items():
            has_questions = agg["questions"] > 0
            pct = (
                round(100 * agg["correct"] / agg["questions"])
                if has_questions
                else None
            )
            sub_list.append(
                SubtopicProgress(
                    subtopic=subtopic_title,
                    mastery_percentage=pct,
                    status=_status_from_pct(
                        pct, has_sessions=True, has_questions=has_questions
                    ),
                    sessions_count=agg["sessions"],
                    last_session_id=agg["last_session_id"],
                )
            )
            t_correct += agg["correct"]
            t_questions += agg["questions"]
            t_sessions += agg["sessions"]

        t_pct = round(100 * t_correct / t_questions) if t_questions > 0 else None
        topics.append(
            TopicProgress(
                topic=topic_title,
                mastery_percentage=t_pct,
                status=_status_from_pct(
                    t_pct, has_sessions=True, has_questions=t_questions > 0
                ),
                sessions_count=t_sessions,
                subtopics=sub_list,
            )
        )

    return ProgressMapResponse(topics=topics)
