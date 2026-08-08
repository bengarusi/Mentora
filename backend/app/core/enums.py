from enum import Enum


class Subject(str, Enum):
    MATH = "math"
    ENGLISH = "english"


class LessonPhase(str, Enum):
    TEACHING = "teaching"
    PRE_PRACTICE_EXAMPLE = "pre_practice_example"
    PRACTICE = "practice"
    PRACTICE_SUMMARY = "practice_summary"
    SUMMARY = "summary"
    COMPLETED = "completed"


class DifficultyLevel(str, Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class SessionStatus(str, Enum):
    ACTIVE = "active"
    ENDED = "ended"


class SuccessLevel(str, Enum):
    ACHIEVED = "achieved"
    PARTIALLY = "partially"
    NOT_ACHIEVED = "not_achieved"


class MessageRole(str, Enum):
    STUDENT = "student"
    TUTOR = "tutor"
