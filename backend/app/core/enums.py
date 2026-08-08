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
    # Homework Help runs as its own single-phase conversation: no teaching →
    # practice ladder, just an open pedagogical dialogue over the uploaded work.
    HOMEWORK_HELP = "homework_help"


class SessionMode(str, Enum):
    """What kind of conversation a LessonSession is. Both modes share the same
    messages, streaming, and voice plumbing — only the phase machine differs."""

    LESSON = "lesson"
    HOMEWORK = "homework"


class MaterialKind(str, Enum):
    """Why a file was uploaded, which decides how it is used later.

    STUDY_MATERIAL files are persistent, topic-tagged resources retrieved on
    demand during normal lessons. HOMEWORK files belong to one Homework Help
    session and are always in that session's context."""

    STUDY_MATERIAL = "study_material"
    HOMEWORK = "homework"


class MaterialStatus(str, Enum):
    """Lifecycle of a material's text extraction / indexing pipeline.

    PENDING and PROCESSING are transient; READY means the text (and chunks) are
    queryable; UNSUPPORTED means no extractor handles this file type yet, and
    FAILED means extraction was attempted and errored."""

    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    UNSUPPORTED = "unsupported"
    FAILED = "failed"


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
