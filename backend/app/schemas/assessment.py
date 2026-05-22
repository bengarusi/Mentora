from pydantic import BaseModel


class QuestionDTO(BaseModel):
    id: int
    difficulty: int
    question_text: str  # criteria intentionally not exposed to the student

    class Config:
        from_attributes = True


class AnswerSubmit(BaseModel):
    question_id: int
    answer: str


class GradedAnswerDTO(BaseModel):
    question_id: int
    is_correct: bool
    feedback: str
    remaining: int  # questions still unanswered in this session


class QuestionResultDTO(BaseModel):
    id: int
    difficulty: int
    question_text: str
    student_answer: str | None = None
    is_correct: bool | None = None
    feedback: str | None = None

    class Config:
        from_attributes = True


class SessionSummary(BaseModel):
    session_id: int
    success_level: str | None = None
    score: int | None = None
    summary_text: str | None = None
    questions: list[QuestionResultDTO] = []
