from __future__ import annotations

import re
from collections.abc import Sequence

from app.agent.schemas import SessionState


_NON_ANSWER_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bi\s+(?:do\s+not|don't)\s+know\b",
        r"\b(?:give|show)\s+me\s+(?:a\s+)?hint\b",
        r"\bexplain(?:\s+it)?\s+again\b",
        r"\bjust\s+tell\s+me\b",
        r"\bnext\s+(?:exercise|question|problem)\b",
        r"\bthanks?\b",
        r"אני\s+לא\s+יודע(?:ת)?",
        r"תן\s+לי\s+רמז|תני\s+לי\s+רמז",
        r"תסביר(?:י)?\s+שוב",
        r"תגיד(?:י)?\s+לי\s+(?:את\s+)?התשובה",
        r"לשאלה\s+הבאה|לתרגיל\s+הבא",
        r"תודה",
    )
)

_HELP_OR_NEXT_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bhelp\b",
        r"\bhint\b",
        r"\bnext\s+(?:exercise|question|problem)\b",
        r"עזר|רמז|הבא",
    )
)


def is_explicit_non_answer(text: str) -> bool:
    normalized = " ".join(text.strip().split())
    return any(pattern.search(normalized) for pattern in _NON_ANSWER_PATTERNS)


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
    return not state.awaiting_response and any(
        ref not in state.solved_refs for ref in outline_refs
    )
