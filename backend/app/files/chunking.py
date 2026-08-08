from __future__ import annotations

import re

# Chunk sizing is a retrieval trade-off: small enough that a hit is specific,
# large enough to keep an explanation intact. Overlap keeps a definition that
# straddles a boundary intact in at least one chunk.
DEFAULT_CHUNK_CHARS = 1200
DEFAULT_OVERLAP_CHARS = 150

_PARAGRAPH_SPLIT = re.compile(r"\n\s*\n")


def normalize_text(text: str) -> str:
    """Collapse the whitespace noise typical of PDF/DOCX extraction while
    preserving paragraph breaks (which carry the document's structure)."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    # Drop the leading/trailing spaces PDF extraction leaves on each line, so
    # they don't survive into chunks (or count against the context budget).
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def chunk_text(
    text: str,
    *,
    chunk_chars: int = DEFAULT_CHUNK_CHARS,
    overlap_chars: int = DEFAULT_OVERLAP_CHARS,
) -> list[str]:
    """Split *text* into overlapping, paragraph-aligned chunks.

    Paragraphs are packed together until the size limit, so chunks break at
    natural boundaries rather than mid-sentence. A single paragraph larger than
    the limit is hard-split as a fallback."""
    text = normalize_text(text)
    if not text:
        return []

    paragraphs = [p.strip() for p in _PARAGRAPH_SPLIT.split(text) if p.strip()]
    chunks: list[str] = []
    current = ""

    def flush() -> None:
        nonlocal current
        if current.strip():
            chunks.append(current.strip())
        current = ""

    for para in paragraphs:
        if len(para) > chunk_chars:
            flush()
            # Oversized paragraph (e.g. a table dumped as one blob): hard-split
            # it with the same overlap so nothing is lost at the seams.
            step = max(1, chunk_chars - overlap_chars)
            for start in range(0, len(para), step):
                piece = para[start : start + chunk_chars].strip()
                if piece:
                    chunks.append(piece)
            continue

        if not current:
            current = para
        elif len(current) + 2 + len(para) <= chunk_chars:
            current = f"{current}\n\n{para}"
        else:
            flush()
            current = para

    flush()

    if overlap_chars <= 0 or len(chunks) < 2:
        return chunks

    # Prepend the tail of each chunk to the next so context spanning a boundary
    # is retrievable from either side.
    overlapped = [chunks[0]]
    for previous, chunk in zip(chunks, chunks[1:]):
        tail = previous[-overlap_chars:].strip()
        overlapped.append(f"{tail}\n\n{chunk}" if tail else chunk)
    return overlapped
