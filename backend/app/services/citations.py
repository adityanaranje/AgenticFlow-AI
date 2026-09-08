"""Citation helpers & validation (Phase 5, §11/§16).

Rejects fabricated document/chunk ids: every stored citation must correspond
to a chunk that was actually retrieved for the given organization during this
research run.
"""

from __future__ import annotations

from typing import Iterable

from app.agents.state import Citation, RetrievedChunk


def format_citation(filename: str, page: int | None = None, chunk: int | None = None) -> str:
    """Render a human citation, e.g. ``[company_policy.pdf, p.12]``.

    No fabrication: returns only what we actually know about the source.
    """
    parts = [filename or "document"]
    if page is not None:
        parts.append(f"p.{page}")
    elif chunk is not None:
        parts.append(f"chunk {chunk}")
    return f"[{', '.join(parts)}]"


def is_grounded(citation: Citation, available: Iterable[RetrievedChunk]) -> bool:
    """True when a citation maps to a chunk actually retrieved this run."""
    for chunk in available:
        if citation.chunk_id and chunk.chunk_id == citation.chunk_id:
            return True
        if (not citation.chunk_id) and chunk.document_id == citation.document_id:
            return True
    return False


def filter_grounded_citations(
    citations: list[Citation], available: list[RetrievedChunk]
) -> tuple[list[Citation], list[Citation]]:
    """Return (grounded, dropped) citations.

    A citation is kept only if its document/chunk was among the retrieved,
    tenant-scoped chunks. Anything else is treated as fabricated and dropped.
    """
    grounded: list[Citation] = []
    dropped: list[Citation] = []
    for citation in citations:
        if is_grounded(citation, available):
            grounded.append(citation)
        else:
            dropped.append(citation)
    return grounded, dropped
