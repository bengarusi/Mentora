from app.llm.provider import TutorContext


def _persona(ctx: TutorContext) -> str:
    level = f" Their level in this subject is {ctx.level}." if ctx.level else ""
    return (
        f"You are Mentora, a patient, encouraging tutor for a grade-{ctx.grade} "
        f"child aged {ctx.age}. Subject: {ctx.subject}. Topic: {ctx.topic}. "
        f"The goal of this lesson is: \"{ctx.goal_text}\".{level} "
        "Always use simple, age-appropriate language, stay positive, and keep "
        "every reply focused on the lesson goal."
    )


def _history(ctx: TutorContext) -> str:
    if not ctx.recent_messages:
        return ""
    lines = [f"{role}: {content}" for role, content in ctx.recent_messages]
    return "\n\nConversation so far:\n" + "\n".join(lines)


def explanation_prompt(ctx: TutorContext) -> tuple[str, str]:
    system = _persona(ctx)
    user = (
        "Explain the topic in a clear, friendly way tied to the lesson goal. "
        "Keep it short (a few sentences), suitable for the child's level."
    )
    return system, user


def example_prompt(ctx: TutorContext) -> tuple[str, str]:
    system = _persona(ctx)
    user = (
        "Give one concrete worked example that illustrates the topic and helps "
        "the child reach the lesson goal. Walk through it step by step, briefly."
        + _history(ctx)
    )
    return system, user


def chat_prompt(ctx: TutorContext, student_message: str) -> tuple[str, str]:
    system = _persona(ctx)
    user = (
        f"{_history(ctx)}\n\nThe student says: \"{student_message}\"\n"
        "Respond helpfully, staying on the lesson goal."
    )
    return system, user


def questions_prompt(ctx: TutorContext) -> tuple[str, str]:
    system = _persona(ctx)
    user = (
        "Create exactly 3 questions to check the student's understanding of the "
        "lesson goal, in increasing difficulty. "
        'Return ONLY JSON of the form: '
        '{"questions": [{"difficulty": 1, "question": "...", "criteria": "..."}, '
        '{"difficulty": 2, ...}, {"difficulty": 3, ...}]}. '
        "The 'criteria' field is the expected answer / grading rubric and is not "
        "shown to the student."
        + _history(ctx)
    )
    return system, user


def grade_prompt(question_text: str, criteria: str, answer: str) -> tuple[str, str]:
    system = (
        "You are a fair, encouraging grader for a child's tutoring session. "
        "Judge the student's answer against the criteria."
    )
    user = (
        f"Question: {question_text}\n"
        f"Grading criteria / expected answer: {criteria}\n"
        f"Student answer: {answer}\n\n"
        'Return ONLY JSON: {"is_correct": true/false, "feedback": "short, kind '
        'feedback explaining why"}.'
    )
    return system, user


def adjust_prompt(ctx: TutorContext, score: int) -> tuple[str, str]:
    system = _persona(ctx)
    user = (
        f"The student answered {score} out of 3 assessment questions correctly. "
        "Recommend whether the next lesson should be harder, easier, or the same, "
        "and give a one-sentence note for the student. "
        'Return ONLY JSON: {"direction": "harder|easier|same", "note": "..."}.'
    )
    return system, user


def summary_prompt(ctx: TutorContext) -> tuple[str, str]:
    system = _persona(ctx)
    user = (
        "Write a short, encouraging summary (2-3 sentences) of what the student "
        "learned in this lesson and how they did, tied to the lesson goal."
        + _history(ctx)
    )
    return system, user
