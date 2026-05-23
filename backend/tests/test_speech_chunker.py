"""Unit tests for SpeechChunker — the latency-oriented text chunking that lets
the tutor start speaking after the first short phrase. Pure logic, no I/O."""

from app.services.speech_chunker import SpeechChunker


def test_first_chunk_emits_at_first_sentence_boundary():
    c = SpeechChunker()
    out = c.add("Great job! That is correct.")
    assert out == ["Great job!"]  # first short phrase emitted immediately
    assert c.flush() == "That is correct."


def test_first_chunk_is_smaller_than_a_normal_chunk():
    c = SpeechChunker(first_chunk_max_len=80, normal_chunk_max_len=200)
    # No boundaries/whitespace → first chunk hard-flushes at first_chunk_max_len.
    first = c.add("a" * 90)
    assert first == ["a" * 80]
    # The next (normal) chunk is allowed to grow to normal_chunk_max_len.
    rest = c.add("b" * 210)  # buffer is "a"*10 + "b"*210
    assert rest == ["a" * 10 + "b" * 190]  # cut at 200, larger than the first chunk


def test_first_chunk_splits_on_colon_and_semicolon():
    assert SpeechChunker().add("Here is the plan: solve it.") == ["Here is the plan:"]
    assert SpeechChunker().add("Step one; then step two.") == ["Step one;"]


def test_first_chunk_splits_on_comma_only_after_min_length():
    # Comma before min_first_chunk_len must NOT split the opener.
    c = SpeechChunker(min_first_chunk_len=40)
    assert c.add("Nice, ") == []
    # Comma past the minimum is allowed for the first chunk.
    c2 = SpeechChunker(min_first_chunk_len=10)
    assert c2.add("Hello there, friend") == ["Hello there,"]


def test_later_chunks_do_not_split_on_commas_or_colons():
    c = SpeechChunker()
    assert c.add("Start. ") == ["Start."]  # flips to normal mode
    # Commas and colons must not break later chunks; no sentence end → nothing yet.
    assert c.add("one, two: three and more") == []
    assert c.flush() == "one, two: three and more"


def test_decimals_are_never_split():
    c = SpeechChunker()
    assert c.add("The answer is 3.14 exactly.") == []  # 3.14's dot is not a boundary
    assert c.flush() == "The answer is 3.14 exactly."

    c2 = SpeechChunker()
    out = c2.add("Values 12.5 and 0.75 work. ")
    assert out == ["Values 12.5 and 0.75 work."]
    assert "12.5" in out[0] and "0.75" in out[0]


def test_newline_emits_a_chunk():
    c = SpeechChunker()
    assert c.add("First line\nsecond") == ["First line"]
    assert c.flush() == "second"


def test_maxlen_fallback_cuts_at_last_whitespace():
    c = SpeechChunker(first_chunk_max_len=12)
    out = c.add("aaaa bbbb cccc dddd eeee")
    assert out == ["aaaa bbbb"]  # cut at whitespace before len 12, no word broken


def test_empty_chunks_are_dropped():
    c = SpeechChunker()
    assert c.add("\n\n\n") == []
    assert c.flush() is None


def test_flush_returns_remainder_without_terminator():
    c = SpeechChunker()
    assert c.add("No terminator here") == []
    assert c.flush() == "No terminator here"


def test_add_can_emit_multiple_chunks_in_one_call():
    c = SpeechChunker()
    assert c.add("One. Two. Three. ") == ["One.", "Two.", "Three."]
