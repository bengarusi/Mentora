from app.core.enums import LessonPhase, MessageRole, SuccessLevel
from app.repositories.message_repo import MessageRepository
from app.schemas.session import SessionCreate
from app.services.tutor_service import TutorService
from tests.conftest import make_student
from tests.fake_llm import FakeLLMProvider


def _service(db):
    student = make_student(db)
    return TutorService(db, FakeLLMProvider(), student), student


def _start(db):
    service, student = _service(db)
    data = SessionCreate(subject="math", topic="Addition", goal_text="Add numbers")
    session = service.create_lesson_and_generate_first_explanation(data)
    return service, session


def test_start_lesson_creates_session_in_explanation_with_first_message(db_session):
    service, session = _start(db_session)
    assert session.phase == LessonPhase.EXPLANATION.value
    messages = MessageRepository(db_session).get_specific_session_messages_history(
        session.id
    )
    assert len(messages) == 1
    assert messages[0].role == MessageRole.TUTOR.value


def test_advance_moves_to_example(db_session):
    service, session = _start(db_session)
    result = service.move_lesson_to_next_phase(session.id)
    assert result.phase == LessonPhase.EXAMPLE.value
    assert result.tutor_message


def test_full_assessment_flow_records_performance(db_session):
    service, session = _start(db_session)
    service.move_lesson_to_next_phase(session.id)  # explanation -> example

    questions = service.begin_assessment_and_generate_questions(session.id)
    assert len(questions) == 3
    assert session.phase == LessonPhase.ASSESSMENT.value

    # answer all 3 correctly (fake grades correct when answer == "correct{difficulty}")
    last = None
    for q in questions:
        last = service.submit_and_grade_assessment_answer(
            session.id, q.id, f"correct{q.difficulty}"
        )
    assert last.remaining == 0

    # finishing the assessment transitions to correction and records performance
    assert session.phase == LessonPhase.CORRECTION.value

    summary = service.get_or_generate_session_summary(session.id)
    assert summary.score == 3
    assert summary.success_level == SuccessLevel.ACHIEVED.value
    assert summary.summary_text  # generated lazily
    assert len(summary.questions) == 3


def test_partial_score_maps_to_partially(db_session):
    service, session = _start(db_session)
    service.move_lesson_to_next_phase(session.id)
    questions = service.begin_assessment_and_generate_questions(session.id)

    # only the first answer correct
    service.submit_and_grade_assessment_answer(session.id, questions[0].id, "correct1")
    service.submit_and_grade_assessment_answer(session.id, questions[1].id, "wrong")
    service.submit_and_grade_assessment_answer(session.id, questions[2].id, "wrong")

    summary = service.get_or_generate_session_summary(session.id)
    assert summary.score == 1
    assert summary.success_level == SuccessLevel.PARTIALLY.value
