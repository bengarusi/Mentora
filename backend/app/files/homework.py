import re

# Matches "Exercise 1:", "Question 2.", "Problem 3" etc. — how the vision/OCR
# and document extractors transcribe most worksheets, and the label the
# homework prompts themselves ask the tutor to use.
_LABELED_EXERCISE = re.compile(r"(?im)^\s*(exercise|question|problem)\s+\d+\b")
# Fallback for worksheets that just number items ("1.", "2)") with no label.
_NUMBERED_ITEM = re.compile(r"(?m)^\s*\d+[.)]\s+\S")


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
