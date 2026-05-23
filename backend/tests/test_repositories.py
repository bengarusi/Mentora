from app.core.enums import LessonPhase, SessionStatus
from app.models.assessment import AssessmentQuestion
from app.models.message import Message
from app.models.session import LessonSession
from app.repositories.assessment_repo import AssessmentRepository
from app.repositories.message_repo import MessageRepository
from app.repositories.performance_repo import PerformanceRepository
from app.repositories.session_repo import SessionRepository
from app.repositories.student_repo import StudentRepository
from app.models.performance import Performance
from tests.conftest import make_student


def _make_session(db, student_id, subject="math"):
    session = LessonSession(
        student_id=student_id,
        subject=subject,
        topic="Topic",
        subtopic="Subtopic",
        goal_text="Goal",
        status=SessionStatus.ACTIVE.value,
        phase=LessonPhase.TEACHING.value,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def test_student_get_by_email(db_session):
    make_student(db_session, email="x@example.com")
    repo = StudentRepository(db_session)
    assert repo.get_by_email("x@example.com") is not None
    assert repo.get_by_email("missing@example.com") is None


def test_session_scoping(db_session):
    a = make_student(db_session, email="a@example.com")
    b = make_student(db_session, email="b@example.com")
    sa = _make_session(db_session, a.id)
    repo = SessionRepository(db_session)

    assert repo.get_specific_session(sa.id, a.id) is not None
    assert repo.get_specific_session(sa.id, b.id) is None
    assert len(repo.get_lesson_list_for_student(a.id)) == 1
    assert len(repo.get_lesson_list_for_student(b.id)) == 0


def test_message_history_is_ordered(db_session):
    student = make_student(db_session)
    session = _make_session(db_session, student.id)
    for i in range(3):
        db_session.add(
            Message(session_id=session.id, role="tutor", content=f"m{i}")
        )
    db_session.commit()

    history = MessageRepository(db_session).get_specific_session_messages_history(
        session.id
    )
    assert [m.content for m in history] == ["m0", "m1", "m2"]


def test_assessment_count_checked_answers(db_session):
    student = make_student(db_session)
    session = _make_session(db_session, student.id)
    db_session.add_all(
        [
            AssessmentQuestion(
                session_id=session.id,
                difficulty=1,
                question_text="q1",
                is_correct=True,
            ),
            AssessmentQuestion(
                session_id=session.id,
                difficulty=2,
                question_text="q2",
                is_correct=None,
            ),
        ]
    )
    db_session.commit()

    repo = AssessmentRepository(db_session)
    assert repo.count_checked_answers(session.id) == 1
    assert [q.difficulty for q in repo.get_specific_session_questions(session.id)] == [
        1,
        2,
    ]


def test_performance_get_for_session(db_session):
    student = make_student(db_session)
    session = _make_session(db_session, student.id)
    db_session.add(
        Performance(session_id=session.id, success_level="achieved", score=3)
    )
    db_session.commit()

    perf = PerformanceRepository(db_session).get_specific_session_performance(
        session.id
    )
    assert perf is not None
    assert perf.score == 3
