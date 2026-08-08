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


class DifficultySelectRequest(BaseModel):
    level: str  # "easy" | "medium" | "hard"


class PhaseResult(BaseModel):
    phase: str
    tutor_message: str | None = None


class TtsRequest(BaseModel):
    text: str


class TtsResult(BaseModel):
    audio_base64: str | None = None


class VoiceTurnResult(BaseModel):
    """Result of a voice turn: the transcribed student speech, the tutor's text
    reply (produced by the unchanged tutor flow), the resulting phase, and an
    optional base64-encoded mp3 of the tutor reply spoken aloud."""

    student_text: str
    tutor_message: str
    phase: str
    audio_base64: str | None = None
