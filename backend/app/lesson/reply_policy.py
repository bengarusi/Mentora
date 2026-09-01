"""Deterministic user-visible safeguards for generated tutor replies."""

from __future__ import annotations

import re
from fractions import Fraction

from app.math.normalizer import canonical_fraction_str, parse_to_fraction
from app.math.router import MathRouterService
from app.math.schemas import ToolResult


_LATEX_FRACTION = re.compile(
    r"\\(?:d?frac)\s*\{\s*(-?\d+)\s*\}\s*\{\s*(\d+)\s*\}"
)
_FINAL_QUESTION = re.compile(
    r"(?:^|[\n.!?;]\s+)(?P<question>[^.!?\n]*\?)",
    re.MULTILINE,
)
_NUMERIC_VALUE = re.compile(
    r"(?<![\w/])-?\d+(?:\s+\d+\s*/\s*\d+|\s*/\s*\d+|\.\d+|%)?(?![\w/])"
)
_SPOKEN_FRACTION = re.compile(
    r"\b(?P<numerator>a|an|one|two|three|four|five|six|seven|eight|nine|ten)\s+"
    r"(?P<denominator>half|halves|third|thirds|quarter|quarters|fourth|fourths|"
    r"fifth|fifths|sixth|sixths|seventh|sevenths|eighth|eighths|ninth|ninths|"
    r"tenth|tenths)\b",
    re.IGNORECASE,
)
_SPOKEN_NUMERATORS = {
    "a": 1,
    "an": 1,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}
_SPOKEN_DENOMINATORS = {
    "half": 2,
    "halves": 2,
    "third": 3,
    "thirds": 3,
    "quarter": 4,
    "quarters": 4,
    "fourth": 4,
    "fourths": 4,
    "fifth": 5,
    "fifths": 5,
    "sixth": 6,
    "sixths": 6,
    "seventh": 7,
    "sevenths": 7,
    "eighth": 8,
    "eighths": 8,
    "ninth": 9,
    "ninths": 9,
    "tenth": 10,
    "tenths": 10,
}
_math_router = MathRouterService()


def _contains_canonical_answer(text: str, canonical_answer: str) -> bool:
    """Whether tutor prose states the server's canonical numeric answer.

    Match the canonical representation, not every mathematically equivalent
    value: in a simplification question the prompt may legitimately repeat the
    given ``25/100`` while the withheld answer is ``1/4``.
    """
    normalized = _LATEX_FRACTION.sub(r"\1/\2", text)
    parsed = parse_to_fraction(canonical_answer)
    answer = (
        canonical_fraction_str(parsed)
        if parsed is not None
        else canonical_answer.strip()
    )
    if not answer:
        return False
    escaped = re.escape(answer).replace(r"/", r"\s*/\s*")
    return (
        re.search(
            rf"(?<![\w./]){escaped}(?![\w/]|\.\d)",
            normalized,
            re.IGNORECASE,
        )
        is not None
    )


def _answer_mentions(text: str) -> list[tuple[Fraction, str]]:
    """Numeric values in prose, paired with a normalized surface form."""
    normalized = _LATEX_FRACTION.sub(r"\1/\2", text)
    mentions: list[tuple[Fraction, str]] = []
    for match in _NUMERIC_VALUE.finditer(normalized):
        surface = match.group(0)
        parsed = parse_to_fraction(surface)
        if parsed is not None:
            mentions.append((parsed, re.sub(r"\s+", "", surface).casefold()))
    for match in _SPOKEN_FRACTION.finditer(normalized):
        numerator = _SPOKEN_NUMERATORS[match.group("numerator").casefold()]
        denominator = _SPOKEN_DENOMINATORS[match.group("denominator").casefold()]
        mentions.append(
            (
                Fraction(numerator, denominator),
                " ".join(match.group(0).casefold().split()),
            )
        )
    return mentions


def _contains_equivalent_answer(
    text: str, canonical_answer: str, *, allowed_source: str = ""
) -> bool:
    """Whether text introduces an answer-equivalent value.

    A simplification hint may repeat the value printed in the question (for
    example ``25/100``) without leaking the withheld ``1/4``. Surface forms
    already present in the source are therefore allowed, while a newly stated
    equivalent such as ``0.25`` or "one quarter" is blocked.
    """
    expected = parse_to_fraction(canonical_answer)
    if expected is None:
        return _contains_canonical_answer(text, canonical_answer)
    allowed_forms = {key for _, key in _answer_mentions(allowed_source)}
    return any(
        value == expected and key not in allowed_forms
        for value, key in _answer_mentions(text)
    )


def _states_equivalent_answer(
    text: str, canonical_answer: str, *, allowed_source: str = ""
) -> bool:
    """Whether a declarative sentence establishes the answer's value."""
    for match in re.finditer(
        r".+?(?:[!?]|[.](?!\d)|\n|$)", text, re.DOTALL
    ):
        sentence = match.group(0).strip()
        if not sentence or sentence.endswith("?"):
            continue
        establishes_value = bool(
            re.search(
                r"(?:=|\bequals?\b|\banswer\s+is\b|\bis\s+the\s+answer\b|"
                r"\bresult\s+is\b|\bis\s+the\s+result\b|\bit\s+is\b|"
                r"\bthat(?:'s|\s+is)\b)",
                sentence,
                re.IGNORECASE,
            )
        )
        if establishes_value and _contains_equivalent_answer(
            sentence, canonical_answer, allowed_source=allowed_source
        ):
            return True
    return False


def _introduces_answer(
    text: str, canonical_answer: str, *, allowed_source: str = ""
) -> bool:
    """Answer literal anywhere, or a newly stated mathematically equivalent value."""
    newly_uses_canonical = _contains_canonical_answer(
        text, canonical_answer
    ) and not _contains_canonical_answer(allowed_source, canonical_answer)
    return newly_uses_canonical or _states_equivalent_answer(
        text, canonical_answer, allowed_source=allowed_source
    )


def ensure_incorrect_reply_is_coherent(
    reply: str,
    verification: ToolResult | None,
    recent_messages: list[tuple[str, str]],
) -> str:
    """Prevent an answer key from being exposed and immediately re-requested.

    Prompts express the teaching policy, but a verified answer is server-held
    data and therefore gets a deterministic output check as well.  If an older
    tutor turn already exposed that answer, asking the student to rediscover it
    is incoherent; acknowledge it and switch to explaining the reasoning.
    """
    if (
        verification is None
        or verification.is_equivalent is not False
        or not verification.canonical_answer
    ):
        return reply

    answer = verification.canonical_answer
    previous_tutor_revealed = any(
        role == "tutor" and _states_equivalent_answer(content, answer)
        for role, content in recent_messages[:-1]
    )
    if previous_tutor_revealed:
        return (
            f"We already established that the answer is {answer}, so I won't ask "
            "you to rediscover it. Which step would you like me to explain?"
        )
    source_question = next(
        (
            content
            for role, content in reversed(recent_messages[:-1])
            if role == "tutor"
        ),
        "",
    )
    if _introduces_answer(reply, answer, allowed_source=source_question):
        return (
            "Not quite yet. Let's take one smaller step: check the operation and "
            "work it through once more. What do you get?"
        )
    return reply


def _self_answered_final_question(reply: str) -> bool:
    """Whether prose before the final arithmetic question states its answer."""
    matches = list(_FINAL_QUESTION.finditer(reply))
    if not matches:
        return False
    final = matches[-1]
    computed = _math_router.verify_chat_answer(final.group("question"), "0")
    if not computed.success or not computed.canonical_answer:
        return False
    return _states_equivalent_answer(
        reply[: final.start("question")], computed.canonical_answer
    )


def ensure_tutor_reply_is_coherent(
    reply: str,
    verification: ToolResult | None,
    recent_messages: list[tuple[str, str]],
) -> str:
    """Apply answer-key and self-answered-question policies to one reply."""
    guarded = ensure_incorrect_reply_is_coherent(
        reply, verification, recent_messages
    )
    if not _self_answered_final_question(guarded):
        return guarded
    if verification is not None and verification.is_equivalent is True:
        return (
            "Correct! Nice work. The next problem's answer was already shown, "
            "so instead, can you explain the first step that makes it true?"
        )
    return (
        "That question already included its answer, so I won't ask you to "
        "repeat it. Can you explain the first step instead?"
    )
