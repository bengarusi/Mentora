from sqlalchemy.orm import Session

from app.core.enums import LessonPhase, SuccessLevel
from app.repositories.performance_repo import PerformanceRepository
from app.repositories.session_repo import SessionRepository
from app.schemas.student_progress import RecentSessionDTO, StudentProgressResponse

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
