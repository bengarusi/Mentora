from __future__ import annotations

_WHITESPACE = " \t\r\n"


class SpeechChunker:
    """Accumulates streamed text deltas and emits TTS-ready chunks at natural
    boundaries, so the tutor can start speaking after the first short phrase
    instead of the full reply.

    The first chunk is deliberately small and aggressive (latency win); later
    chunks are conservative. Decimal numbers (e.g. ``3.14``) are never split:
    a ``.`` only counts as a boundary when the next buffered char is whitespace,
    and the char after a decimal point is always a digit.
    """

    def __init__(
        self,
        *,
        first_chunk_max_len: int = 80,
        normal_chunk_max_len: int = 200,
        min_first_chunk_len: int = 40,
    ) -> None:
        self.first_chunk_max_len = first_chunk_max_len
        self.normal_chunk_max_len = normal_chunk_max_len
        self.min_first_chunk_len = min_first_chunk_len
        self.first_done = False
        self.buffer = ""

    def add(self, delta: str) -> list[str]:
        """Append a text delta and return any chunks that are now ready."""
        self.buffer += delta
        out: list[str] = []
        while True:
            chunk = self._extract()
            if chunk is None:
                break
            if chunk:  # non-empty after strip; empty means only whitespace was consumed
                out.append(chunk)
        return out

    def flush(self) -> str | None:
        """Return the trailing remainder at stream end (a final sentence whose
        terminator has no following whitespace, or a terminal decimal)."""
        remainder = self.buffer.strip()
        self.buffer = ""
        if remainder:
            self.first_done = True
            return remainder
        return None

    # ---- internals ----

    def _extract(self) -> str | None:
        """Pop one ready chunk from the front of the buffer, or None if none is
        ready yet. May return an empty string when only whitespace was consumed."""
        buf = self.buffer
        if not buf:
            return None
        max_len = self.normal_chunk_max_len if self.first_done else self.first_chunk_max_len
        cut = self._find_boundary(buf)
        if cut is None and len(buf) >= max_len:
            cut = self._maxlen_cut(buf, max_len)
        if cut is None:
            return None
        chunk = buf[:cut]
        self.buffer = buf[cut:]
        stripped = chunk.strip()
        if stripped:
            self.first_done = True
        return stripped

    def _find_boundary(self, buf: str) -> int | None:
        """Index just past the earliest acceptable boundary, or None."""
        soft = not self.first_done
        n = len(buf)
        for i, ch in enumerate(buf):
            if ch == "\n":
                return i + 1
            nxt_is_ws = i + 1 < n and buf[i + 1] in _WHITESPACE
            if ch in ".!?":
                if nxt_is_ws:  # decimal-safe: char after a decimal point is a digit
                    return i + 1
            elif soft and ch in ":;":
                if nxt_is_ws:
                    return i + 1
            elif soft and ch == ",":
                if nxt_is_ws and (i + 1) >= self.min_first_chunk_len:
                    return i + 1
        return None

    def _maxlen_cut(self, buf: str, max_len: int) -> int:
        """Cut at the last whitespace before max_len; hard-cut if none."""
        window = buf[:max_len]
        ws = max(window.rfind(" "), window.rfind("\n"), window.rfind("\t"))
        if ws > 0:
            return ws + 1
        return max_len
