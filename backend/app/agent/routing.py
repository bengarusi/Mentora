from __future__ import annotations

import re
from collections.abc import Sequence

from app.agent.schemas import SessionState


#: Apostrophes: students type "dont", phones autocorrect to "don't", and some
#: keyboards produce the curly U+2019. All three must read the same, or the
#: plainest way to say "I'm stuck" gets force-graded as a wrong math answer.
_APOS = r"['‘’ʼ]?"

#: "I am stuck, do something about it." These need the agent — only an agent turn
#: climbs the help ladder — and each one raises the hint level.
_PLEA_FOR_HELP_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        rf"\bi\s+(?:do\s+not|do{_APOS}nt|don{_APOS}t|dun{_APOS}?no|dunno)\s*(?:know)?\b",
        r"\bidk\b",
        r"\bno\s+(?:idea|clue)\b",
        # A bare plea for help, with or without padding: "help", "help me",
        # "i need help", "can you help me?".
        r"\bhelp\b",
        r"\b(?:i\s*'?m\s+|im\s+)?(?:stuck|lost|confused)\b",
        r"\b(?:give|show)\s+me\s+(?:a\s+)?hint\b",
        r"\bhint\b",
        r"\bexplain(?:\s+it)?\s+again\b",
        r"\bexplain\s+the\s+method\b",
        r"\bjust\s+tell\s+me\b",
        r"\bwhat\s+do\s+(?:i|you)\s+(?:do|mean)\b",
        r"\bhow\s+do\s+i\b",
        rf"\bi\s+(?:can{_APOS}?t|cannot)\b",
        r"אני\s+לא\s+יודע(?:ת)?",
        r"לא\s+יודע(?:ת)?",
        r"אין\s+לי\s+מושג",
        r"תן\s+לי\s+רמז|תני\s+לי\s+רמז",
        r"רמז",
        r"עזרה|תעזור|תעזרי|תסביר(?:י)?\s+שוב",
        r"תגיד(?:י)?\s+לי\s+(?:את\s+)?התשובה",
        r"נתקעתי|לא\s+הבנתי",
    )
)

#: Not an answer either, but not a cry for help: courtesies and "move me along".
#: These must not raise the hint level — thanking the tutor is not being stuck.
_OTHER_NON_ANSWER_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bnext\s+(?:exercise|question|problem)\b",
        r"\bthanks?\b",
        r"לשאלה\s+הבאה|לתרגיל\s+הבא",
        r"תודה",
    )
)

_NON_ANSWER_PATTERNS = _PLEA_FOR_HELP_PATTERNS + _OTHER_NON_ANSWER_PATTERNS

_HELP_OR_NEXT_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bhelp\b",
        r"\bhint\b",
        r"\bnext\s+(?:exercise|question|problem)\b",
        r"עזר|רמז|הבא",
    )
)


#: Asking to leave the current exercise for now. The quick action on the
#: homework screen sends the first of these verbatim.
_SKIP_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bready\s+for\s+the\s+next\b",
        r"\bnext\s+(?:exercise|question|problem|one)\b",
        r"\b(?:skip|move\s+on|come\s+back\s+to\s+(?:this|it))\b",
        r"\bleave\s+(?:this|it)\s+for\s+(?:now|later)\b",
        r"לתרגיל\s+הבא|לשאלה\s+הבאה|לדלג|תדלג|נדלג|לעבור\s+הלאה",
    )
)


def wants_to_skip(text: str) -> bool:
    """Whether the student is asking to leave this exercise for now."""
    normalized = " ".join(text.strip().split())
    return any(pattern.search(normalized) for pattern in _SKIP_PATTERNS)


#: A digit, or a number written as a word, anywhere in the message. This is what
#: separates "I need help" from "56, but I needed help for it" — the second is an
#: attempt and must still be graded, however the student padded it.
_CARRIES_A_NUMBER = re.compile(
    r"\d"
    r"|\b(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve"
    r"|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty"
    r"|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred"
    r"|half|halves|third|thirds|quarter|quarters|fourth|fourths)\b",
    re.IGNORECASE,
)


def carries_an_attempt(text: str) -> bool:
    """Whether the message contains a number the grader could rule on."""
    return bool(_CARRIES_A_NUMBER.search(text))


def is_explicit_non_answer(text: str) -> bool:
    """Whether the student is asking for help rather than offering an answer.

    A message carrying a number is an attempt no matter what else it says, so
    "56, but I needed help" is still graded. Everything else that reads as a
    plea — "i dont know", "help", "idk" — must NOT reach the math grader: it
    cannot parse a number out of prose, and the student is then told "please
    send just your answer as a number" for a message that was never an answer.
    """
    normalized = " ".join(text.strip().split())
    if carries_an_attempt(normalized):
        return False
    return any(pattern.search(normalized) for pattern in _NON_ANSWER_PATTERNS)


def is_plea_for_help(text: str) -> bool:
    """Whether the student is stuck and asking for help.

    Narrower than :func:`is_explicit_non_answer`: "thanks" is not an answer but
    is not a cry for help either, and must neither wake the agent nor spend a
    rung of the help ladder.
    """
    normalized = " ".join(text.strip().split())
    if carries_an_attempt(normalized):
        return False
    return any(pattern.search(normalized) for pattern in _PLEA_FOR_HELP_PATTERNS)


def should_evaluate_answer(text: str, state: SessionState) -> bool:
    return bool(
        state.awaiting_response
        and state.response_target is not None
        and text.strip()
        and not is_explicit_non_answer(text)
    )


def might_need_tools(
    text: str, state: SessionState, *, outline_refs: Sequence[str]
) -> bool:
    """Whether this turn needs the agent, or the cheaper chat reply will do.

    The gap between exercises belongs to the agent too. Only an agent turn can
    arm the next target, so a session that answers one exercise correctly and
    then says "yes" to "shall we do the next one?" would otherwise hand every
    remaining turn to the plain chat path — which grades nothing, records
    nothing and can never arm a target again. The solved counter then stops at
    one however much work the student does.
    """
    if should_evaluate_answer(text, state):
        return True
    if not outline_refs:
        return True
    if any(pattern.search(text) for pattern in _HELP_OR_NEXT_PATTERNS):
        return True
    # Every recognised plea for help needs the agent, not the cheap chat reply:
    # only an agent turn climbs the help ladder, so a student saying "i dont
    # know" or "נתקעתי" on the fast path would get the same rung — and so the
    # same words — back for as long as they kept asking. Reading the shared plea
    # list keeps this from drifting away from the grader veto again. A mere
    # courtesy ("thanks") is not a plea, and still takes the cheap path.
    if is_plea_for_help(text):
        return True
    return not state.awaiting_response and any(
        ref not in state.solved_refs for ref in outline_refs
    )
