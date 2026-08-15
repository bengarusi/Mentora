from app.agent.evaluation import AnswerEvaluator
from app.agent.schemas import HomeworkExercise
from app.llm.provider import LLMError
from app.math.schemas import ToolResult


class RaisingGrader:
    def grade_chat_answer(self, question_text: str, student_answer: str):
        raise AssertionError("deterministic answers must not consult the LLM")


def test_fraction_equivalence_is_authoritative_without_llm():
    evaluator = AnswerEvaluator(RaisingGrader())
    outline = [HomeworkExercise("exercise-1", "Simplify 2/4", "1/2")]

    result = evaluator.evaluate("0.5", "exercise-1", outline)

    assert result.verdict is True
    assert result.authoritative is True
    assert result.correct_answer == "1/2"
    assert result.tool_used == "fraction_arithmetic"


def test_reasoned_answer_with_one_numeric_candidate_is_checked_deterministically():
    evaluator = AnswerEvaluator(RaisingGrader())
    outline = [HomeworkExercise("exercise-1", "Simplify 18/30", "3/5")]

    result = evaluator.evaluate(
        "I simplified it and got 3/5",
        "exercise-1",
        outline,
    )

    assert result.verdict is True
    assert result.authoritative is True


def test_model_extraction_is_not_part_of_the_authoritative_tool_schema(db_session):
    from app.agent.registry import ToolRegistry
    from app.models.session import LessonSession
    from tests.conftest import make_student

    student = make_student(db_session)
    session = LessonSession(
        student_id=student.id,
        subject="math",
        topic="Homework Help",
        subtopic="Fractions",
        goal_text="Finish",
        mode="homework",
        phase="homework_help",
    )
    db_session.add(session)
    db_session.flush()
    schema = next(
        item for item in ToolRegistry(db_session, RaisingGrader(), student, session).schemas()
        if item.name == "evaluateAnswer"
    )

    assert "extracted_answer" not in str(schema.parameters)


def test_ambiguous_numbers_never_become_an_authoritative_wrong_answer():
    from app.schemas.tutor import ChatAnswerGrade

    class AbstainingGrader:
        def grade_chat_answer(self, question_text: str, student_answer: str):
            return ChatAnswerGrade(is_correct=None)

    result = AnswerEvaluator(AbstainingGrader()).evaluate(
        "3/5 because I cancelled 18/30 by 6",
        "exercise-1",
        [HomeworkExercise("exercise-1", "Simplify 18/30", "3/5")],
    )

    assert result.verdict is None
    assert result.authoritative is False


def test_expected_answer_abstention_continues_to_other_deterministic_evaluators():
    class CascadingRouter:
        def validate_student_answer(self, question, expected, answer):
            return ToolResult(False, "validator", is_equivalent=None)

        def verify_chat_answer(self, question, answer):
            return ToolResult(
                True,
                "chat_arithmetic",
                canonical_answer="4",
                is_equivalent=True,
            )

    result = AnswerEvaluator(RaisingGrader(), router=CascadingRouter()).evaluate(
        "4", "exercise-1", [HomeworkExercise("exercise-1", "What is 2 + 2?", "four")]
    )

    assert result.verdict is True
    assert result.authoritative is True
    assert result.tool_used == "chat_arithmetic"


def test_unresolved_question_abstains_without_guessing():
    evaluator = AnswerEvaluator(RaisingGrader())

    result = evaluator.evaluate("3/4", "missing", [])

    assert result.verdict is None
    assert result.authoritative is False
    assert result.reason == "unresolved_question"


def test_equation_without_stored_answer_is_solved_deterministically():
    evaluator = AnswerEvaluator(RaisingGrader())
    outline = [HomeworkExercise("exercise-1", "Solve 2*x + 3 = 7")]

    result = evaluator.evaluate("x = 2", "exercise-1", outline)

    assert result.verdict is True
    assert result.authoritative is True
    assert result.tool_used == "sympy_equation"


def test_non_math_fallback_is_advisory():
    from app.schemas.tutor import ChatAnswerGrade

    class Grader:
        def grade_chat_answer(self, question_text: str, student_answer: str):
            return ChatAnswerGrade(is_correct=True, correct_answer="because it is even")

    evaluator = AnswerEvaluator(Grader())
    outline = [HomeworkExercise("exercise-1", "Explain why the number is even")]

    result = evaluator.evaluate("because it divides by two", "exercise-1", outline)

    assert result.verdict is True
    assert result.authoritative is False
    assert result.tool_used == "llm_fallback"


def test_grader_failure_abstains_cleanly():
    class FailedGrader:
        def grade_chat_answer(self, question_text: str, student_answer: str):
            raise LLMError("offline")

    result = AnswerEvaluator(FailedGrader()).evaluate(
        "an explanation", "exercise-1", [HomeworkExercise("exercise-1", "Explain why")]
    )

    assert result.verdict is None
    assert result.authoritative is False


def test_incorrect_observation_hides_answer_key_and_steps_from_model():
    result = AnswerEvaluator(RaisingGrader()).evaluate(
        "1/3",
        "exercise-1",
        [HomeworkExercise("exercise-1", "What is 1/2 + 1/4?", "3/4")],
    )

    observation = result.as_observation()

    assert observation["verdict"] == "incorrect"
    assert "correct_answer" not in observation
    assert "steps" not in observation
