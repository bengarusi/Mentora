from app.agent.reducer import StateReducer
from app.agent.schemas import Annotation, MasteryDelta, ResponseTarget, SessionState
from app.agent.stores import SessionStateStore, StudentProgressStore
from app.models.student_mastery import StudentSkillMastery
from tests.conftest import make_student


def test_session_state_round_trips_json_fields(db_session):
    student = make_student(db_session)
    from app.models.session import LessonSession

    lesson = LessonSession(
        student_id=student.id,
        subject="math",
        topic="Fractions",
        subtopic="Equivalent fractions",
        goal_text="Finish homework",
        mode="homework",
        phase="homework_help",
    )
    db_session.add(lesson)
    db_session.commit()
    state = SessionState(
        session_id=lesson.id,
        current_exercise_index=2,
        awaiting_response=True,
        response_target=ResponseTarget("exercise-2-step-1", "substep"),
        solved_refs=frozenset({"exercise-1"}),
        annotations=(Annotation("misconception", "added denominators", "fractions"),),
    )

    SessionStateStore(db_session).save(state)
    db_session.commit()
    db_session.expire_all()
    loaded = SessionStateStore(db_session).load(lesson.id)

    assert loaded == state


def test_mastery_survives_across_sessions_and_uses_only_evidence(db_session):
    student = make_student(db_session)
    store = StudentProgressStore(db_session)

    store.apply(
        student_id=student.id,
        subject="math",
        topic="Fractions",
        delta=MasteryDelta("equivalence", True),
    )
    store.apply(
        student_id=student.id,
        subject="math",
        topic="Fractions",
        delta=MasteryDelta("equivalence", False),
    )
    db_session.commit()
    db_session.expire_all()

    row = db_session.query(StudentSkillMastery).one()
    assert row.attempts == 2
    assert row.correct == 1
    assert row.mastery_estimate == 0.5
    assert row.open_misconceptions == []


def test_model_annotation_never_changes_mastery(db_session):
    student = make_student(db_session)
    state = SessionState(session_id=999)

    StateReducer.annotate(
        state, Annotation("misconception", "subtracted denominators", "fractions")
    )

    assert (
        db_session.query(StudentSkillMastery)
        .filter(StudentSkillMastery.student_id == student.id)
        .count()
        == 0
    )
