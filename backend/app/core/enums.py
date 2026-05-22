from enum import Enum


class Subject(str, Enum):
    MATH = "math"
    ENGLISH = "english"


class LessonPhase(str, Enum):
    EXPLANATION = "explanation"
    EXAMPLE = "example"
    ASSESSMENT = "assessment"
    CORRECTION = "correction"
    LEVEL_ADJUSTMENT = "level_adjustment"
    COMPLETED = "completed"


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
