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


# ---- API request / response DTOs for the tutor flow ----

class TurnRequest(BaseModel):
    content: str


class TurnResult(BaseModel):
    tutor_message: str
    phase: str


class PhaseResult(BaseModel):
    phase: str
    tutor_message: str | None = None
