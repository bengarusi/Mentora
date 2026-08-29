import re

# Matches "Exercise 1:", "Question 2.", "Problem 3" etc. — how the vision/OCR
# and document extractors transcribe most worksheets, and the label the
# homework prompts themselves ask the tutor to use.
_LABELED_EXERCISE = re.compile(r"(?im)^\s*(exercise|question|problem)\s+\d+\b")
# Fallback for worksheets that just number items ("1.", "2)") with no label.
_NUMBERED_ITEM = re.compile(r"(?m)^\s*\d+[.)]\s+\S")
_LABELED_START = re.compile(
    r"(?im)^\s*(?:exercise|question|problem)\s+(\d+)\b"
)
_NUMBERED_START = re.compile(r"(?m)^\s*(\d+)[.)]\s+\S")
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


def count_exercises(text: str) -> int:
    """Best-effort count of distinct exercises in a homework document.

    Deterministic and free — this only counts lines, it never needs an LLM
    call. Falls back from labeled exercises to bare numbered items, and
    finally to "the whole thing is one exercise" for unstructured text, so a
    single free-form question still gets a sane total instead of zero."""
    if not text or not text.strip():
        return 0
    labeled = len(_LABELED_EXERCISE.findall(text))
    if labeled:
        return labeled
    numbered = len(_NUMBERED_ITEM.findall(text))
    if numbered:
        return numbered
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
    matches = list(_LABELED_START.finditer(text))
    if not matches:
        matches = list(_NUMBERED_START.finditer(text))
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
