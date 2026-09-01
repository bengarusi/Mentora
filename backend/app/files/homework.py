import re

# Matches "Exercise 1:", "Question 2.", "Problem 3" etc. — how the vision/OCR
# and document extractors transcribe most worksheets, and the label the
# homework prompts themselves ask the tutor to use.
_LABELED_START = re.compile(
    r"(?im)^[ \t]*(?:exercise|question|problem)\s+(\d+)\b"
)
# Worksheets and OCR commonly mix labels with bare numbering (for example,
# ``Question 1`` followed by ``2.`` through ``7)``).  These are candidates even
# when a labeled marker exists; ``_top_level_starts`` decides which candidates
# are questions and which are nested numbered steps.
_NUMBERED_START = re.compile(r"(?m)^[ \t]*(\d+)[.)]\s+\S")
_EXPECTED_ANSWER = re.compile(
    r"(?i)\b(?:answer|solution)\s*[:=]\s*([^\n;]+?)\s*$"
)


_ARITHMETIC_REWRITES = (
    # "7 x 8" and "7 × 8" are how worksheets write multiplication; the math
    # parser only knows "*". The digit on both sides is what keeps this off
    # algebra — the x in "2x + 3 = 11" has no digit after it.
    (re.compile(r"(?<=\d)\s*[x×✕✖]\s*(?=\d)"), " * "),
    (re.compile(r"(?<=\d)\s*[÷]\s*(?=\d)"), " / "),
    (re.compile("[−–—]"), "-"),  # unicode minus and dashes
)


def normalize_arithmetic(text: str) -> str:
    """Rewrite a worksheet's arithmetic into what the math parser reads.

    Only for computing and checking answers — the student is still shown the
    question as their worksheet wrote it.
    """
    for pattern, replacement in _ARITHMETIC_REWRITES:
        text = pattern.sub(replacement, text)
    return text


def _top_level_starts(text: str) -> list[re.Match[str]]:
    """Return ordered structural boundaries for top-level questions.

    Labeled boundaries are authoritative.  A bare numbered boundary is merged
    when its number fits strictly between the nearest labeled numbers (or
    continues after the final label).  That recovers mixed OCR such as
    ``Question 1`` + ``2.`` ... ``7.`` without turning the ``1.``/``2.`` working
    steps inside ``Exercise 1`` into separate exercises before ``Exercise 2``.
    """
    labeled = list(_LABELED_START.finditer(text))
    numbered = list(_NUMBERED_START.finditer(text))
    if not labeled:
        return numbered

    starts: list[re.Match[str]] = list(labeled)
    for candidate in numbered:
        number = int(candidate.group(1))
        previous = next(
            (match for match in reversed(labeled) if match.start() < candidate.start()),
            None,
        )
        following = next(
            (match for match in labeled if match.start() > candidate.start()),
            None,
        )
        lower = int(previous.group(1)) if previous is not None else None
        upper = int(following.group(1)) if following is not None else None
        # A local restart at/below the labeled number signals a numbered
        # working-step list. Once seen, later larger step numbers in that same
        # labeled region are nested too; without this, ``Exercise 1`` followed
        # by steps 1, 2, 3 became three separate exercises. Mixed OCR such as
        # ``Question 1`` followed directly by top-level 2, 3 has no restart and
        # remains recoverable.
        nested_restart = bool(
            previous is not None
            and lower is not None
            and any(
                previous.start() < match.start() < candidate.start()
                and int(match.group(1)) <= lower
                for match in numbered
            )
        )
        if (
            not nested_restart
            and (lower is None or number > lower)
            and (upper is None or number < upper)
        ):
            starts.append(candidate)
    return sorted(starts, key=lambda match: match.start())


def count_exercises(text: str) -> int:
    """Best-effort count of distinct exercises in a homework document.

    Deterministic and free — this only counts lines, it never needs an LLM
    call. Falls back from labeled exercises to bare numbered items, and
    finally to "the whole thing is one exercise" for unstructured text, so a
    single free-form question still gets a sane total instead of zero."""
    if not text or not text.strip():
        return 0
    starts = _top_level_starts(text)
    if starts:
        return len(starts)
    return 1


def segment_exercises(text: str) -> list[dict[str, str | None]]:
    """Split a worksheet into stable server-held exercise references.

    This is deliberately structural rather than semantic: labels and numbered
    lines determine boundaries. An explicit ``Answer:`` suffix is captured as
    evidence; otherwise the expected answer remains unknown for deterministic
    extraction by the math router or a later content pipeline.
    """
    if not text or not text.strip():
        return []
    matches = _top_level_starts(text)
    if not matches:
        matches = [None]

    outline: list[dict[str, str | None]] = []
    for index, match in enumerate(matches, start=1):
        start = match.start() if match is not None else 0
        next_match = matches[index] if index < len(matches) else None
        end = next_match.start() if next_match is not None else len(text)
        body = text[start:end].strip()
        answer_match = _EXPECTED_ANSWER.search(body)
        expected = answer_match.group(1).strip().rstrip(".") if answer_match else None
        if answer_match:
            body = body[: answer_match.start()].strip().rstrip()
        outline.append(
            {
                "ref": f"exercise-{index}",
                "text": body,
                "expected_answer": expected,
                "target_type": "exercise",
                "skill": None,
            }
        )
    return outline
