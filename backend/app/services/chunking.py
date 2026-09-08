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
from dataclasses import dataclass, field
from typing import Any, Optional

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
    page_number: Optional[int] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def char_count(self) -> int:
        return len(self.content)

    @property
    def token_estimate(self) -> int:
        return max(1, round(len(self.content) / _CHARS_PER_TOKEN))


def _split_paragraphs(page: ParsedPage) -> list[tuple[Optional[int], str]]:
    """Split a page into (page_number, paragraph) non-empty segments."""
    segments: list[tuple[Optional[int], str]] = []
    for raw in _PARAGRAPH_SPLIT.split(page.text):
        paragraph = raw.strip()
        if paragraph:
            segments.append((page.page_number, paragraph))
    return segments


def chunk_pages(
    pages: list[ParsedPage],
    *,
    chunk_size: Optional[int] = None,
    chunk_overlap: Optional[int] = None,
    extra_metadata: Optional[dict[str, Any]] = None,
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
    segments: list[tuple[Optional[int], str]] = []
    for page in pages:
        segments.extend(_split_paragraphs(page))
    if not segments:
        return []

    n = len(segments)
    lengths = [len(text) for _, text in segments]
    base_metadata = dict(extra_metadata or {})
    chunks: list[TextChunk] = []

    start = 0
    while start < n:
        # Grow a window of paragraphs up to `size` characters.
        length = lengths[start]
        end = start + 1
        while end < n:
            if length + 2 + lengths[end] > size:
                break
            length += 2 + lengths[end]
            end += 1

        content = "\n\n".join(text for _, text in segments[start:end]).strip()
        if content:
            chunks.append(
                TextChunk(
                    chunk_index=len(chunks),
                    content=content,
                    page_number=segments[start][0],
                    metadata=dict(base_metadata),
                )
            )

        if end >= n:
            break

        # Advance the window start so the next chunk keeps ~`overlap` chars
        # of this chunk's tail for continuity, while still moving forward.
        next_start = end
        tail = 0
        for k in range(end - 1, start - 1, -1):
            tail += lengths[k] + 2
            if tail >= overlap:
                next_start = k
                break
        if next_start >= end:  # overlap smaller than any paragraph
            next_start = end - 1
        if next_start <= start:  # guarantee forward progress
            next_start = start + 1
        start = next_start

    return chunks


def chunk_text(
    text: str,
    *,
    chunk_size: Optional[int] = None,
    chunk_overlap: Optional[int] = None,
    extra_metadata: Optional[dict[str, Any]] = None,
) -> list[TextChunk]:
    """Convenience: chunk a single normalized text blob."""
    return chunk_pages(
        [ParsedPage(text=text, page_number=None)],
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        extra_metadata=extra_metadata,
    )
