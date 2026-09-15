"""Report persistence (Phase 5, §12).

Turns a completed :class:`ResearchState` into a stored ``reports`` row plus
its validated ``report_sources`` mapping. Only grounded citations are stored;
fabricated ones are dropped (see :mod:`app.services.citations`).
"""

from __future__ import annotations

from typing import Any

from app.agents.state import ResearchState
from app.core.config import settings
from app.core.logging import get_logger
from app.db.repositories.reports import ReportRepository
from app.db.supabase import get_supabase
from app.services import citations

logger = get_logger(__name__)


def _section_text(state: ResearchState, heading: str) -> str | None:
    for section in state.sections:
        if section.heading.strip().lower() == heading.strip().lower():
            return section.body.strip()
    return None


def _existing_document_ids(document_ids: set[str], organization_id: str) -> set[str]:
    """Return the subset of *document_ids* that actually exist in the
    ``documents`` table for the given organization.

    The ``report_sources.document_id`` foreign key references
    ``documents.id``; if a document was deleted between retrieval and report
    storage the insert would violate the constraint.  This helper filters
    stale references so only valid foreign keys are written.
    """
    if not document_ids:
        return set()

    client = get_supabase()
    if client is None:
        # Can't verify — play it safe and drop all document references.
        return set()

    existing: set[str] = set()
    # Supabase ``in_`` filter accepts a comma-separated list; batch to stay
    # well within URL length limits for large citation sets.
    batch_size = 50
    id_list = list(document_ids)
    for start in range(0, len(id_list), batch_size):
        batch = id_list[start : start + batch_size]
        try:
            resp = (
                client.table("documents")
                .select("id")
                .eq("organization_id", organization_id)
                .in_("id", batch)
                .execute()
            )
            for row in (resp.data or []):
                existing.add(str(row["id"]))
        except Exception:
            logger.warning("Failed to verify document_ids batch; skipping stale refs in this batch.")
    return existing


def _store_sources(repo: ReportRepository, rows: list[dict[str, Any]]) -> None:
    """Persist citation rows in bulk, falling back to one insert per row.

    Repositories without the bulk helper (test doubles, older callers) keep
    working exactly as before.
    """
    if not rows:
        return

    bulk = getattr(repo, "create_sources", None)
    if not callable(bulk):
        for row in rows:
            repo.create_source(row)
        return

    size = max(1, int(settings.report_source_batch_size))
    for start in range(0, len(rows), size):
        bulk(rows[start : start + size])


def store_report(state: ResearchState) -> dict[str, Any] | None:
    """Persist a report + sources. Returns the stored report row or None."""
    repo = ReportRepository()

    title = _section_text(state, "Research Question") or state.original_query
    if title and len(title) > 120:
        title = title[:120]
    summary = _section_text(state, "Executive Summary")

    # Sections JSON for structured display.
    sections = {section.heading: section.body for section in state.sections}
    # Ensure the report has a non-empty body.
    content = (state.final_report or "").strip() or state.original_query

    report = repo.create(
        research_run_id=state.research_id,
        organization_id=state.organization_id,
        title=title or "Research report",
        content=content,
        summary=summary,
        confidence=state.confidence,
        sections=sections,
    )
    if not report:
        logger.error("Failed to store report for research %s", state.research_id)
        return None

    report_id = report["id"]

    # Persist only grounded citations (tenant-scoped retrieved chunks).
    grounded, dropped = citations.filter_grounded_citations(
        state.citations, state.retrieved
    )
    # Look up retrieval score for relevance metrics.
    score_by_chunk = {c.chunk_id: c.score for c in state.retrieved if c.chunk_id}

    # Validate that referenced document_ids actually exist in the DB.
    # A document may have been deleted between retrieval and report storage;
    # inserting a stale foreign key violates report_sources_document_id_fkey.
    cited_doc_ids = {c.document_id for c in grounded if c.document_id}
    valid_doc_ids = _existing_document_ids(cited_doc_ids, state.organization_id)

    source_rows = [
        {
            "report_id": report_id,
            "source_type": "internal",
            "document_id": citation.document_id if citation.document_id in valid_doc_ids else None,
            "chunk_id": citation.chunk_id or None,
            "url": None,
            "title": citation.filename,
            "citation": citations.format_citation(
                citation.filename, citation.page_number, citation.chunk_index
            ),
            "metadata": {
                "page_number": citation.page_number,
                "chunk_index": citation.chunk_index,
                "citation_label": citation.citation_label,
                "retrieval_score": score_by_chunk.get(citation.chunk_id),
            },
        }
        for citation in grounded
    ]
    _store_sources(repo, source_rows)
    if dropped:
        logger.warning(
            "Dropped %d fabricated citation(s) for research %s",
            len(dropped),
            state.research_id,
        )

    return report
