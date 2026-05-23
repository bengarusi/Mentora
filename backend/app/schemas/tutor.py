from pydantic import BaseModel


# ---- Structured outputs returned by the LLM provider ----

class GeneratedPracticeQuestion(BaseModel):
    difficulty: int       # 1, 2, 3 = relative difficulty within the set
    question: str
    correct_answer: str   # exact expected answer
    solution_steps: str   # step-by-step solution text
    explanation: str      # why this approach / what the student should understand


class GradedAnswer(BaseModel):
    is_correct: bool
    feedback: str         # short, child-friendly sentence


class ChatAnswerGrade(BaseModel):
    """Verdict for a free-form teaching-chat answer, used to lock the tutor's
    reply so it can't mark a correct answer wrong."""

    is_correct: bool | None   # None = the message wasn't an answer / couldn't grade
    correct_answer: str | None = None


# ---- API request / response DTOs for the tutor flow ----

class TurnRequest(BaseModel):
    content: str


class TurnResult(BaseModel):
    tutor_message: str
    phase: str


class PhaseResult(BaseModel):
    phase: str
    tutor_message: str | None = None
