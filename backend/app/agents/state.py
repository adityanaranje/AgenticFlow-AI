"""Typed state for the agentic research workflow (Phase 5, §4).

The workflow manipulates a :class:`ResearchState`. Node functions receive the
state and return an updated copy (they are intentionally side-effect free and
pure w.r.t. the state object; persistence + progress live in the runner).

These dataclasses are also (de)serialized into ``research_runs.graph_state``
so the frontend can show safe progress.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

# Safe statuses surfaced to the UI.
RESEARCH_STATUSES = (
    "queued",
    "planning",
    "retrieving",
    "analyzing",
    "checking_gaps",
    "synthesizing",
    "validating",
    "completed",
    "failed",
    "cancelled",
)


@dataclass
class RetrievedChunk:
    """One chunk retrieved from the (tenant-scoped) knowledge base."""

    document_id: str
    chunk_id: str  # DB document_chunks.id == Qdrant vector point id
    content: str
    filename: str = ""
    page_number: Optional[int] = None
    chunk_index: Optional[int] = None
    score: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class EvidenceItem:
    """A source-supported evidence claim."""

    claim: str
    supporting_source: str  # human-readable source label, e.g. filename + page
    document_id: str
    chunk_id: str
    supporting_chunk: str  # verbatim chunk text supporting the claim
    confidence: float = 0.0
    filename: str = ""
    page_number: Optional[int] = None
    chunk_index: Optional[int] = None


@dataclass
class Citation:
    """A validated citation mapping to an actual retrieved document/chunk."""

    document_id: str
    chunk_id: str
    filename: str
    page_number: Optional[int] = None
    chunk_index: Optional[int] = None
    citation_text: str = ""
    citation_label: str = ""


@dataclass
class ReportSection:
    heading: str
    body: str


@dataclass
class ResearchState:
    research_id: str = ""
    organization_id: str = ""
    user_id: str = ""

    original_query: str = ""
    config: dict[str, Any] = field(default_factory=dict)

    sub_questions: list[str] = field(default_factory=list)
    search_queries: list[str] = field(default_factory=list)
    used_queries: list[str] = field(default_factory=list)

    retrieved: list[RetrievedChunk] = field(default_factory=list)
    evidence: list[EvidenceItem] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)

    draft: str = ""
    citations: list[Citation] = field(default_factory=list)

    sections: list[ReportSection] = field(default_factory=list)
    final_report: str = ""
    confidence: Optional[float] = None

    status: str = "queued"
    errors: list[str] = field(default_factory=list)
    iteration: int = 0

    def to_jsonable(self) -> dict[str, Any]:
        """Serialize for ``graph_state`` JSON (safe fields only)."""

        def chunk_json(c: RetrievedChunk) -> dict[str, Any]:
            return {
                "document_id": c.document_id,
                "chunk_id": c.chunk_id,
                "content": c.content[:4000],
                "filename": c.filename,
                "page_number": c.page_number,
                "chunk_index": c.chunk_index,
                "score": c.score,
            }

        def ev_json(e: EvidenceItem) -> dict[str, Any]:
            return {
                "claim": e.claim[:4000],
                "supporting_source": e.supporting_source,
                "document_id": e.document_id,
                "chunk_id": e.chunk_id,
                "supporting_chunk": e.supporting_chunk[:4000],
                "confidence": e.confidence,
            }

        def cite_json(c: Citation) -> dict[str, Any]:
            return {
                "document_id": c.document_id,
                "chunk_id": c.chunk_id,
                "filename": c.filename,
                "page_number": c.page_number,
                "chunk_index": c.chunk_index,
                "citation_text": c.citation_text,
                "citation_label": c.citation_label,
            }

        return {
            "research_id": self.research_id,
            "organization_id": self.organization_id,
            "user_id": self.user_id,
            "original_query": self.original_query,
            "status": self.status,
            "iteration": self.iteration,
            "sub_questions": self.sub_questions[:50],
            "search_queries": self.search_queries[:100],
            "retrieved_count": len(self.retrieved),
            "retrieved": [chunk_json(c) for c in self.retrieved[:200]],
            "evidence_count": len(self.evidence),
            "evidence": [ev_json(e) for e in self.evidence[:200]],
            "gaps": self.gaps[:50],
            "citations_count": len(self.citations),
            "citations": [cite_json(c) for c in self.citations[:200]],
            "final_report": (self.final_report or "")[:200_000],
            "confidence": self.confidence,
            "errors": self.errors[-20:],
        }


def from_jsonable(data: dict[str, Any]) -> ResearchState:
    """Rebuild a ResearchState from a JSONable dict (used on resume/review)."""
    state = ResearchState(
        research_id=data.get("research_id", ""),
        organization_id=data.get("organization_id", ""),
        user_id=data.get("user_id", ""),
        original_query=data.get("original_query", ""),
        config=data.get("config", {}),
        status=data.get("status", "queued"),
        iteration=int(data.get("iteration", 0)),
    )
    for c in data.get("retrieved", []):
        state.retrieved.append(
            RetrievedChunk(
                document_id=c.get("document_id", ""),
                chunk_id=c.get("chunk_id", ""),
                content=c.get("content", ""),
                filename=c.get("filename", ""),
                page_number=c.get("page_number"),
                chunk_index=c.get("chunk_index"),
                score=float(c.get("score", 0.0)),
            )
        )
    for e in data.get("evidence", []):
        state.evidence.append(
            EvidenceItem(
                claim=e.get("claim", ""),
                supporting_source=e.get("supporting_source", ""),
                document_id=e.get("document_id", ""),
                chunk_id=e.get("chunk_id", ""),
                supporting_chunk=e.get("supporting_chunk", ""),
                confidence=float(e.get("confidence", 0.0)),
            )
        )
    for c in data.get("citations", []):
        state.citations.append(
            Citation(
                document_id=c.get("document_id", ""),
                chunk_id=c.get("chunk_id", ""),
                filename=c.get("filename", ""),
                page_number=c.get("page_number"),
                chunk_index=c.get("chunk_index"),
                citation_text=c.get("citation_text", ""),
                citation_label=c.get("citation_label", ""),
            )
        )
    state.final_report = data.get("final_report", "")
    state.gaps = list(data.get("gaps", []))
    state.errors = list(data.get("errors", []))
    return state
