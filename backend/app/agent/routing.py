from __future__ import annotations

import re

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


def might_need_tools(text: str, state: SessionState, *, has_outline: bool) -> bool:
    if should_evaluate_answer(text, state):
        return True
    if not has_outline:
        return True
    return any(pattern.search(text) for pattern in _HELP_OR_NEXT_PATTERNS)
