from pydantic import BaseModel


class PracticeQuestionDTO(BaseModel):
    id: int
    difficulty: int
    question_text: str
    set_number: int

    class Config:
        from_attributes = True


class PracticeAnswerItem(BaseModel):
    question_id: int
    answer: str


class PracticeAnswersSubmit(BaseModel):
    answers: list[PracticeAnswerItem]


class GradedPracticeItem(BaseModel):
    question_id: int
    question_text: str
    difficulty: int
    set_number: int
    student_answer: str
    is_correct: bool
    feedback: str
    correct_answer: str | None = None
    solution_steps: str | None = None
    explanation: str | None = None

    class Config:
        from_attributes = True


class PracticeSetResult(BaseModel):
    set_number: int
    questions: list[GradedPracticeItem]


class PracticeSummaryDTO(BaseModel):
    session_id: int
    total_correct: int
    total_questions: int
    success_level: str | None = None
    sets: list[PracticeSetResult]


class PracticeStartResult(BaseModel):
    set_number: int
    questions: list[PracticeQuestionDTO]


class PracticeSubmitResult(BaseModel):
    set_number: int
    grades: list[GradedPracticeItem]
