from app.core.enums import LessonPhase, MessageRole, SuccessLevel
from app.repositories.message_repo import MessageRepository
from app.schemas.practice import PracticeAnswerItem, PracticeAnswersSubmit
from app.schemas.session import SessionCreate
from app.services.tutor_service import TutorService
from tests.conftest import make_student
from tests.fake_llm import FakeLLMProvider


def _service(db):
    student = make_student(db)
    return TutorService(db, FakeLLMProvider(), student), student


def _start(db):
    service, student = _service(db)
    data = SessionCreate(
        subject="math",
        topic="Fractions",
        subtopic="Adding fractions",
        goal_text="Learn fractions",
    )
    session = service.create_lesson_and_generate_first_explanation(data)
    return service, session


def test_start_lesson_creates_session_in_teaching_with_first_message(db_session):
    service, session = _start(db_session)
    assert session.phase == LessonPhase.TEACHING.value
    messages = MessageRepository(db_session).get_specific_session_messages_history(
        session.id
    )
    assert len(messages) == 1
    assert messages[0].role == MessageRole.TUTOR.value


def test_advance_teaching_moves_to_pre_practice_example(db_session):
    service, session = _start(db_session)
    result = service.move_lesson_to_next_phase(session.id)
    assert result.phase == LessonPhase.PRE_PRACTICE_EXAMPLE.value
    assert result.tutor_message  # guided example text was generated


def test_start_practice_transitions_to_practice_and_returns_questions(db_session):
    service, session = _start(db_session)
    service.move_lesson_to_next_phase(session.id)  # → PRE_PRACTICE_EXAMPLE

    result = service.start_practice(session.id)
    assert session.phase == LessonPhase.PRACTICE.value
    assert result.set_number == 1
    assert len(result.questions) == 3


def test_submit_practice_set_grades_all_three(db_session):
    service, session = _start(db_session)
    service.move_lesson_to_next_phase(session.id)  # → PRE_PRACTICE_EXAMPLE
    first_set = service.start_practice(session.id)

    # correct answers are "correct1", "correct2", "correct3" per FakeLLMProvider
    answers = PracticeAnswersSubmit(
        answers=[
            PracticeAnswerItem(question_id=q.id, answer=f"correct{q.difficulty}")
            for q in first_set.questions
        ]
    )
    result = service.submit_practice_set(session.id, answers)

    assert result.set_number == 1
    assert len(result.grades) == 3
    assert all(g.is_correct for g in result.grades)
    assert all(g.correct_answer for g in result.grades)
    assert all(g.solution_steps for g in result.grades)


def test_next_practice_set_increments_set_number(db_session):
    service, session = _start(db_session)
    service.move_lesson_to_next_phase(session.id)
    first_set = service.start_practice(session.id)

    # Submit set 1
    answers = PracticeAnswersSubmit(
        answers=[
            PracticeAnswerItem(question_id=q.id, answer=f"correct{q.difficulty}")
            for q in first_set.questions
        ]
    )
    service.submit_practice_set(session.id, answers)

    # Get set 2
    second_set = service.next_practice_set(session.id)
    assert second_set.set_number == 2
    assert len(second_set.questions) == 3


def test_finish_practice_records_performance_and_moves_to_summary(db_session):
    service, session = _start(db_session)
    service.move_lesson_to_next_phase(session.id)
    first_set = service.start_practice(session.id)

    # Answer all correctly
    answers = PracticeAnswersSubmit(
        answers=[
            PracticeAnswerItem(question_id=q.id, answer=f"correct{q.difficulty}")
            for q in first_set.questions
        ]
    )
    service.submit_practice_set(session.id, answers)
    result = service.finish_practice(session.id)

    assert result.phase == LessonPhase.PRACTICE_SUMMARY.value

    # Practice summary should show 3/3
    summary = service.get_practice_summary(session.id)
    assert summary.total_questions == 3
    assert summary.total_correct == 3
    assert summary.success_level == SuccessLevel.ACHIEVED.value
    assert len(summary.sets) == 1
    assert len(summary.sets[0].questions) == 3


def test_partial_score_maps_to_partially(db_session):
    service, session = _start(db_session)
    service.move_lesson_to_next_phase(session.id)
    first_set = service.start_practice(session.id)

    # Only first answer correct
    answers = PracticeAnswersSubmit(
        answers=[
            PracticeAnswerItem(question_id=first_set.questions[0].id, answer="correct1"),
            PracticeAnswerItem(question_id=first_set.questions[1].id, answer="wrong"),
            PracticeAnswerItem(question_id=first_set.questions[2].id, answer="wrong"),
        ]
    )
    service.submit_practice_set(session.id, answers)
    service.finish_practice(session.id)

    summary = service.get_practice_summary(session.id)
    assert summary.total_correct == 1
    assert summary.total_questions == 3
    assert summary.success_level == SuccessLevel.PARTIALLY.value


def test_advance_from_practice_summary_generates_lesson_summary(db_session):
    service, session = _start(db_session)
    service.move_lesson_to_next_phase(session.id)
    first_set = service.start_practice(session.id)

    answers = PracticeAnswersSubmit(
        answers=[
            PracticeAnswerItem(question_id=q.id, answer=f"correct{q.difficulty}")
            for q in first_set.questions
        ]
    )
    service.submit_practice_set(session.id, answers)
    service.finish_practice(session.id)

    # Advance: PRACTICE_SUMMARY → SUMMARY (generates final summary message)
    result = service.move_lesson_to_next_phase(session.id)
    assert result.phase == LessonPhase.SUMMARY.value
    assert result.tutor_message  # lesson summary was generated
