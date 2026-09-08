"""Citation validator node (Phase 5, §5/§11).

Confirms every citation in the report maps to an actual retrieved document +
chunk. Fabricated references (labels with no backing evidence) are rejected
and recorded so they are never stored as real citations.
"""

from __future__ import annotations

import re

from app.agents.context import ResearchServices
from app.agents.state import Citation, ResearchState

# Matches [E0], [E12], etc. (the citation labels the synthesis is told to use)
_CITE_RE = re.compile(r"\[E(\d+)\]")


def extract_citations(text: str) -> list[int]:
    """Return the set of evidence indices referenced in ``text``."""
    seen: list[int] = []
    for m in _CITE_RE.finditer(text or ""):
        idx = int(m.group(1))
        if idx not in seen:
            seen.append(idx)
    return seen


def citation_validator_node(
    state: ResearchState, services: ResearchServices
) -> ResearchState:
    """Map in-text citations to real evidence chunks; drop the fabricated ones."""
    state.status = "validating"

    referenced = extract_citations(state.draft)
    evidence = state.evidence

    valid: list[Citation] = []
    invalid: list[int] = []

    for idx in referenced:
        if idx < 0 or idx >= len(evidence):
            invalid.append(idx)
            continue
        ev = evidence[idx]
        citation = Citation(
            document_id=ev.document_id,
            chunk_id=ev.chunk_id,
            filename=ev.filename or ev.supporting_source,
            page_number=ev.page_number,
            chunk_index=ev.chunk_index,
            citation_text=f"[E{idx}]",
            citation_label=f"E{idx}",
        )
        valid.append(citation)

    state.citations = valid

    if invalid:
        state.errors.append(
            f"Dropped {len(invalid)} fabricated citation(s): " + ", ".join(str(i) for i in invalid[:10])
        )

    return state
