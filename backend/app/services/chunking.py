"""Recursive paragraph-aware chunking (Phase 4, §8).

Input is the structural output of the parser (a list of :class:`ParsedPage`).
Text is split into paragraphs; paragraphs are accumulated into chunks of
roughly ``chunk_size`` characters with ``chunk_overlap`` characters carried
over between neighbours, avoiding both tiny and oversized chunks.

Every chunk records provenance so report citations can be produced later
without fabricating sources:

    - ``chunk_index``
    - ``content``
    - ``char_count`` / ``token_estimate`` (approximate)
    - ``page_number`` (the page the chunk begins on, when known)
    - ``metadata`` (extensible)

Configuration comes from :mod:`app.core.config` (``CHUNK_SIZE``,
``CHUNK_OVERLAP``) — no magic numbers.
"""

from __future__ import annotations

import re
from bisect import bisect_right
from dataclasses import dataclass, field
from typing import Any

from app.core.config import settings
from app.services.document_parser import ParsedPage

# Approximate English token density (chars -> tokens). Good enough for
# reporting and budget checks; not used for exact tokenization.
_CHARS_PER_TOKEN = 4

# A chunk much smaller than this is not worth embedding on its own.
_MIN_CHUNK_CHARS = 200

_PARAGRAPH_SPLIT = re.compile(r"\n{2,}")


@dataclass
class TextChunk:
    """One chunk ready for embedding and storage."""

    chunk_index: int
    content: str
    page_number: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def char_count(self) -> int:
        return len(self.content)

    @property
    def token_estimate(self) -> int:
        return max(1, round(len(self.content) / _CHARS_PER_TOKEN))


def _split_paragraphs(page: ParsedPage) -> list[tuple[int | None, str]]:
    """Split a page into (page_number, paragraph) non-empty segments."""
    segments: list[tuple[int | None, str]] = []
    page_number = page.page_number
    append = segments.append
    for raw in _PARAGRAPH_SPLIT.split(page.text):
        paragraph = raw.strip()
        if paragraph:
            append((page_number, paragraph))
    return segments


def chunk_pages(
    pages: list[ParsedPage],
    *,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
    extra_metadata: dict[str, Any] | None = None,
) -> list[TextChunk]:
    """Chunk a list of parsed pages into overlapping :class:`TextChunk`.

    Uses a paragraph-token sliding window: chunks never cut through a
    paragraph and neighbouring chunks overlap by roughly ``chunk_overlap``
    characters so context is preserved across boundaries. A chunk's
    ``page_number`` is the page of the paragraph that *starts* it.
    """
    size = chunk_size or settings.chunk_size
    overlap = chunk_overlap if chunk_overlap is not None else settings.chunk_overlap

    if size <= 0:
        raise ValueError("chunk_size must be positive")
    if overlap < 0 or overlap >= size:
        raise ValueError("chunk_overlap must be >= 0 and < chunk_size")

    # Ordered (page, paragraph) tokens across all pages.
    segments: list[tuple[int | None, str]] = []
    for page in pages:
        segments.extend(_split_paragraphs(page))
    if not segments:
        return []

    n = len(segments)
    base_metadata = dict(extra_metadata or {})

    # Prefix sums of (paragraph length + separator). ``prefix[i]`` is the
    # length of paragraphs 0..i-1 joined by "\n\n" *including* the trailing
    # separator, so a window [start, end) measures prefix[end] - prefix[start] - 2.
    # This turns both the "how many paragraphs fit in `size`" growth step and
    # the "which paragraph starts the overlap tail" back-scan into a single
    # binary search instead of re-walking the paragraphs of every chunk
    # (which degraded to quadratic behaviour on documents with many short
    # paragraphs, i.e. exactly the big files where chunking must stay fast).
    prefix = [0] * (n + 1)
    running = 0
    for index, (_, text) in enumerate(segments):
        running += len(text) + 2
        prefix[index + 1] = running

    # Texts only; the loop below reads them positionally.
    texts = [text for _, text in segments]
    pages_of = [page for page, _ in segments]
    chunks: list[TextChunk] = []
    append = chunks.append

    start = 0
    while start < n:
        # Largest window that fits `size`: the biggest `end` whose paragraphs
        # satisfy prefix[end] - prefix[start] - 2 + 2 + len(segments[end]) <= size.
        limit = size + prefix[start] + 2
        end = min(bisect_right(prefix, limit) - 1, n)
        # A single paragraph longer than `size` still forms one chunk.
        end = max(end, start + 1)

        content = "\n\n".join(texts[start:end])
        if content:
            append(
                TextChunk(
                    chunk_index=len(chunks),
                    content=content,
                    page_number=pages_of[start],
                    metadata=dict(base_metadata),
                )
            )

        if end >= n:
            break

        # Advance the window start so the next chunk keeps ~`overlap` chars
        # of this chunk's tail for continuity, while still moving forward.
        # k is the largest paragraph index in [start, end-1] whose tail
        # (prefix[end] - prefix[k]) reaches `overlap` — found by binary
        # search instead of walking the window paragraph by paragraph.
        k = min(bisect_right(prefix, prefix[end] - overlap) - 1, end - 1)
        if k < start:
            next_start = end - 1  # the whole chunk tail is shorter than overlap
        elif k == start:
            next_start = start + 1  # overlap reached only at the chunk head
        else:
            next_start = k
        if next_start >= end:  # overlap smaller than any paragraph
            next_start = end - 1
        if next_start <= start:  # guarantee forward progress
            next_start = start + 1
        start = next_start

    return chunks


def chunk_text(
    text: str,
    *,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
    extra_metadata: dict[str, Any] | None = None,
) -> list[TextChunk]:
    """Convenience: chunk a single normalized text blob."""
    return chunk_pages(
        [ParsedPage(text=text, page_number=None)],
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        extra_metadata=extra_metadata,
    )
