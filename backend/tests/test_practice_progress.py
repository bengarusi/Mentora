"""Progress is earned by answering practice questions, and only that way.

Three rules are pinned here: a question is written at the level the chat last
settled on, a correct answer is worth 1 / 3 / 5 percent by that level, and a
question already answered correctly is closed to further scoring.
"""

from app.core.enums import DifficultyLevel, LessonPhase
from app.models.assessment import AssessmentQuestion
from app.repositories.assessment_repo import AssessmentRepository
from app.schemas.practice import PracticeAnswerItem, PracticeAnswersSubmit
from app.schemas.session import SessionCreate
from app.services.progress_service import get_progress_map
from app.services.tutor_service import TutorService
from tests.conftest import make_student
from tests.fake_llm import FakeLLMProvider


def _lesson(db, student, *, topic="Fractions", subtopic="Adding fractions"):
    service = TutorService(db, FakeLLMProvider(), student)
    session = service.create_lesson_and_generate_first_explanation(
        SessionCreate(
            subject="math",
            topic=topic,
            subtopic=subtopic,
            goal_text="Learn fractions",
        )
    )
    return service, session


def _practice(service, session, level: str | None = None):
    """Take a lesson to its first practice set, optionally picking a level."""
    if level is not None:
        service.set_lesson_difficulty(session.id, level)
    service.move_lesson_to_next_phase(session.id)  # → PRE_PRACTICE_EXAMPLE
    return service.start_practice(session.id)


def _all_correct(questions) -> PracticeAnswersSubmit:
    # FakeLLMProvider answers each question with "correct{difficulty}".
    return PracticeAnswersSubmit(
        answers=[
            PracticeAnswerItem(question_id=q.id, answer=f"correct{q.difficulty}")
            for q in questions
        ]
    )


def _subtopic_pct(db, student_id, topic, subtopic) -> int:
    topics = get_progress_map(db, student_id).topics
    row = next(t for t in topics if t.topic == topic)
    return next(s for s in row.subtopics if s.subtopic == subtopic).mastery_percentage


# ---------------------------------------------------------------------------
# Practice follows the level the student chose in the chat
# ---------------------------------------------------------------------------

def test_questions_are_written_at_the_level_chosen_in_chat(db_session):
    student = make_student(db_session)
    service, session = _lesson(db_session, student)
    first_set = _practice(service, session, level="easy")

    questions = AssessmentRepository(db_session).get_practice_set_questions(session.id, 1)
    assert len(questions) == len(first_set.questions)
    assert {q.level for q in questions} == {DifficultyLevel.EASY.value}


def test_switching_level_mid_lesson_carries_into_the_next_set(db_session):
    student = make_student(db_session)
    service, session = _lesson(db_session, student)
    service.set_lesson_difficulty(session.id, "easy")
    service.set_lesson_difficulty(session.id, "hard")  # the "increase difficulty" path
    _practice(service, session)

    questions = AssessmentRepository(db_session).get_practice_set_questions(session.id, 1)
    assert {q.level for q in questions} == {DifficultyLevel.HARD.value}


def test_a_question_keeps_its_level_when_the_lesson_moves_on(db_session):
    """The lesson's level is a moving target; a banked answer is not."""
    student = make_student(db_session)
    service, session = _lesson(db_session, student)
    _practice(service, session, level="easy")

    session.difficulty = DifficultyLevel.HARD.value
    db_session.commit()

    questions = AssessmentRepository(db_session).get_practice_set_questions(session.id, 1)
    assert {q.level for q in questions} == {DifficultyLevel.EASY.value}


# ---------------------------------------------------------------------------
# What a correct answer is worth
# ---------------------------------------------------------------------------

def test_correct_answers_are_worth_one_three_and_five_percent(db_session):
    student = make_student(db_session)
    for level, expected in (("easy", 3), ("medium", 9), ("hard", 15)):
        subtopic = f"{level} work"
        service, session = _lesson(db_session, student, subtopic=subtopic)
        first_set = _practice(service, session, level=level)
        service.submit_practice_set(session.id, _all_correct(first_set.questions))

        # Three questions per set, each correct.
        assert _subtopic_pct(db_session, student.id, "Fractions", subtopic) == expected


def test_a_wrong_answer_earns_nothing(db_session):
    student = make_student(db_session)
    service, session = _lesson(db_session, student)
    first_set = _practice(service, session, level="hard")

    service.submit_practice_set(
        session.id,
        PracticeAnswersSubmit(
            answers=[
                PracticeAnswerItem(question_id=q.id, answer="nope")
                for q in first_set.questions
            ]
        ),
    )

    assert _subtopic_pct(db_session, student.id, "Fractions", "Adding fractions") == 0


def test_progress_stops_at_one_hundred(db_session):
    student = make_student(db_session)
    service, session = _lesson(db_session, student)
    _practice(service, session, level="hard")

    # 25 hard answers is 125 points' worth of work; the bar is still full, not
    # overfull, and the extra practice is allowed rather than blocked.
    for _ in range(25):
        db_session.add(
            AssessmentQuestion(
                session_id=session.id,
                set_number=99,
                difficulty=1,
                level=DifficultyLevel.HARD.value,
                question_text="q",
                is_correct=True,
            )
        )
    db_session.commit()

    assert _subtopic_pct(db_session, student.id, "Fractions", "Adding fractions") == 100


def test_teaching_alone_earns_nothing(db_session):
    """A lesson can be read end to end; progress starts at the practice."""
    student = make_student(db_session)
    service, session = _lesson(db_session, student)
    service.set_lesson_difficulty(session.id, "hard")
    service.send_student_message_and_get_tutor_reply(session.id, "I get it now")

    assert _subtopic_pct(db_session, student.id, "Fractions", "Adding fractions") == 0


def test_topic_percentage_averages_its_subtopics(db_session):
    student = make_student(db_session)
    for subtopic, level in (("Adding fractions", "hard"), ("Comparing fractions", "easy")):
        service, session = _lesson(db_session, student, subtopic=subtopic)
        first_set = _practice(service, session, level=level)
        service.submit_practice_set(session.id, _all_correct(first_set.questions))

    topic = next(
        t for t in get_progress_map(db_session, student.id).topics if t.topic == "Fractions"
    )
    # (15 + 3) / 2 — the frontend spreads this over the full curriculum instead.
    assert topic.mastery_percentage == 9


# ---------------------------------------------------------------------------
# A correct answer is banked once
# ---------------------------------------------------------------------------

def test_answering_a_correct_question_again_earns_nothing(db_session):
    student = make_student(db_session)
    service, session = _lesson(db_session, student)
    first_set = _practice(service, session, level="hard")
    answers = _all_correct(first_set.questions)

    service.submit_practice_set(session.id, answers)
    service.submit_practice_set(session.id, answers)

    assert _subtopic_pct(db_session, student.id, "Fractions", "Adding fractions") == 15


def test_resubmitting_cannot_undo_a_correct_answer(db_session):
    student = make_student(db_session)
    service, session = _lesson(db_session, student)
    first_set = _practice(service, session, level="medium")
    service.submit_practice_set(session.id, _all_correct(first_set.questions))

    result = service.submit_practice_set(
        session.id,
        PracticeAnswersSubmit(
            answers=[
                PracticeAnswerItem(question_id=q.id, answer="rubbish")
                for q in first_set.questions
            ]
        ),
    )

    assert all(g.is_correct for g in result.grades)
    questions = AssessmentRepository(db_session).get_practice_set_questions(session.id, 1)
    assert all(q.student_answer != "rubbish" for q in questions)
    assert _subtopic_pct(db_session, student.id, "Fractions", "Adding fractions") == 9


def test_a_wrong_answer_can_still_be_retried(db_session):
    student = make_student(db_session)
    service, session = _lesson(db_session, student)
    first_set = _practice(service, session, level="medium")
    wrong = PracticeAnswersSubmit(
        answers=[
            PracticeAnswerItem(question_id=q.id, answer="nope")
            for q in first_set.questions
        ]
    )

    service.submit_practice_set(session.id, wrong)
    result = service.submit_practice_set(session.id, _all_correct(first_set.questions))

    assert all(g.is_correct for g in result.grades)
    assert session.phase == LessonPhase.PRACTICE.value
    assert _subtopic_pct(db_session, student.id, "Fractions", "Adding fractions") == 9
