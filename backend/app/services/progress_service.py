from sqlalchemy.orm import Session

from app.core.enums import DifficultyLevel, LessonPhase, SuccessLevel
from app.repositories.assessment_repo import AssessmentRepository
from app.repositories.performance_repo import PerformanceRepository
from app.repositories.session_repo import SessionRepository
from app.schemas.student_progress import (
    ProgressMapResponse,
    RecentSessionDTO,
    StudentProgressResponse,
    SubtopicProgress,
    TopicProgress,
)

#: Progress earned by answering one practice question correctly, by the level it
#: was asked at. Harder questions are worth more because they are worth more —
#: 20 correct hard answers complete a subtopic where easy ones take 100.
_POINTS_BY_LEVEL: dict[str, int] = {
    DifficultyLevel.EASY.value: 1,
    DifficultyLevel.MEDIUM.value: 3,
    DifficultyLevel.HARD.value: 5,
}
#: Questions written before the level was recorded score as medium.
_DEFAULT_POINTS = _POINTS_BY_LEVEL[DifficultyLevel.MEDIUM.value]

#: Points are progress percent, so a subtopic is complete at 100. Past that a
#: student can keep practising; it simply stops adding.
_COMPLETE = 100


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

    for session in sessions:
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
        # Every lesson, not just the newest few: the history list pages back
        # through all of them, and a lesson on page three needs its score as
        # much as one on page one.
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


def _status_from_pct(pct: int, *, has_sessions: bool) -> str:
    """Progress only ever climbs, so there is no failing band to report.

    "Not started" belongs to a subtopic nobody has opened; once a lesson exists
    the student is under way whether or not they have banked a point yet.
    """
    if not has_sessions:
        return "not_started"
    if pct >= _COMPLETE:
        return "mastered"
    return "in_progress"


def _normalize_subtopic(title: str | None) -> str:
    return (title or "General").strip() or "General"


def get_progress_map(db: Session, student_id: int) -> ProgressMapResponse:
    """Group the student's sessions by (topic, subtopic) and compute progress %.

    Progress is earned one practice question at a time: a correct answer is worth
    1, 3 or 5 percent depending on the level it was asked at, and a subtopic is
    complete at 100. Nothing else moves the number — teaching, chatting and
    reaching a later lesson phase are how a student gets to the questions, not
    progress in themselves.

    Sessions come back newest-first, so the first one seen per subtopic is the
    most recent (used for `last_session_id`). The frontend overlays this onto the
    full curriculum so not-started topics still appear — which is also why the
    topic figure here averages only the subtopics that have been opened. The
    curriculum-relative topic figure is the frontend's to compute, since only it
    knows how many subtopics a topic is supposed to have."""
    sessions = SessionRepository(db).get_lesson_list_for_student(student_id)

    # (topic, subtopic) -> progress percent earned, before the 100 cap.
    earned: dict[tuple[str, str], int] = {}
    for topic, subtopic, level, count in AssessmentRepository(
        db
    ).count_correct_by_topic_and_level(student_id):
        key = (topic, _normalize_subtopic(subtopic))
        earned[key] = earned.get(key, 0) + count * _POINTS_BY_LEVEL.get(
            level or "", _DEFAULT_POINTS
        )

    # topic_title -> subtopic_title -> aggregate
    topic_map: dict[str, dict[str, dict]] = {}
    for s in sessions:
        subtopic_title = _normalize_subtopic(getattr(s, "subtopic", None))
        subs = topic_map.setdefault(s.topic, {})
        agg = subs.setdefault(
            subtopic_title,
            {"sessions": 0, "last_session_id": None},
        )
        agg["sessions"] += 1
        if agg["last_session_id"] is None:
            agg["last_session_id"] = s.id

    topics: list[TopicProgress] = []
    for topic_title, subs in topic_map.items():
        sub_list: list[SubtopicProgress] = []
        for subtopic_title, agg in subs.items():
            pct = min(_COMPLETE, earned.get((topic_title, subtopic_title), 0))
            sub_list.append(
                SubtopicProgress(
                    subtopic=subtopic_title,
                    mastery_percentage=pct,
                    status=_status_from_pct(pct, has_sessions=True),
                    sessions_count=agg["sessions"],
                    last_session_id=agg["last_session_id"],
                )
            )

        t_pct = round(sum(s.mastery_percentage or 0 for s in sub_list) / len(sub_list))
        topics.append(
            TopicProgress(
                topic=topic_title,
                mastery_percentage=t_pct,
                status=_status_from_pct(t_pct, has_sessions=True),
                sessions_count=sum(agg["sessions"] for agg in subs.values()),
                subtopics=sub_list,
            )
        )

    return ProgressMapResponse(topics=topics)
