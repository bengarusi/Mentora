from pydantic import BaseModel


# ---- Structured outputs returned by the LLM provider ----

class GeneratedQuestion(BaseModel):
    difficulty: int  # 1, 2, 3 = increasing
    question: str
    criteria: str  # rubric / expected answer used for grading


class GeneratedQuestions(BaseModel):
    questions: list[GeneratedQuestion]


class GradedAnswer(BaseModel):
    is_correct: bool
    feedback: str


class LevelAdjustment(BaseModel):
    direction: str  # "harder" | "easier" | "same"
    note: str


# ---- API request / response DTOs for the tutor flow ----

class TurnRequest(BaseModel):
    content: str


class TurnResult(BaseModel):
    tutor_message: str
    phase: str


class PhaseResult(BaseModel):
    phase: str
    tutor_message: str | None = None
