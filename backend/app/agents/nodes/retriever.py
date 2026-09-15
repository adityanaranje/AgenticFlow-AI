"""Retriever node (Phase 5, §5/§7)."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.agents.context import ResearchServices
from app.agents.state import ResearchState, RetrievedChunk


@dataclass
class _QueryResult:
    """Outcome of one query: chunks found, or a failure flag."""

    chunks: list[RetrievedChunk] = field(default_factory=list)
    failed: bool = False


def _merge_unique(existing: list[RetrievedChunk], incoming: list[RetrievedChunk]):
    seen = {c.chunk_id for c in existing}
    for chunk in incoming:
        if chunk.chunk_id and chunk.chunk_id not in seen:
            existing.append(chunk)
            seen.add(chunk.chunk_id)
        elif not chunk.chunk_id and chunk.document_id not in seen:
            existing.append(chunk)
            seen.add(chunk.document_id)
    return existing


def _sequential_results(
    services: ResearchServices,
    organization_id: str,
    pending: list[str],
    top_k: int,
) -> list[_QueryResult]:
    """Per-query retrieval, isolating failures to the query that failed."""
    results: list[_QueryResult] = []
    for query in pending:
        try:
            chunks = services.retrieve(organization_id, query, top_k, {})
            results.append(_QueryResult(chunks=list(chunks or [])))
        except Exception:
            results.append(_QueryResult(failed=True))
    return results


def _retrieve_pending(
    services: ResearchServices,
    organization_id: str,
    pending: list[str],
    top_k: int,
) -> list[_QueryResult]:
    """Retrieve every pending query, preserving query order.

    Uses the batch collaborator when the caller provides one (one embeddings
    request plus concurrent vector searches instead of one round trip per
    query). A failure of the batch call falls back to per-query retrieval so
    a single bad query cannot lose every other query's evidence.
    """
    if services.retrieve_many is not None:
        try:
            batches = services.retrieve_many(organization_id, pending, top_k, {})
            if len(batches) == len(pending):
                return [_QueryResult(chunks=list(batch or [])) for batch in batches]
        except Exception:
            pass  # fall back to the per-query path, which isolates failures
    return _sequential_results(services, organization_id, pending, top_k)


def retriever_node(state: ResearchState, services: ResearchServices) -> ResearchState:
    """Retrieve evidence for every open query, scoped to the organization.

    Retrieval is always filtered by ``organization_id`` (enforced inside
    ``services.retrieve`` → Phase 4 vector store), so the agent can never
    reach another tenant's chunks.

    All open queries are resolved together (embedding + vector search for
    each, bounded by ``RETRIEVAL_CONCURRENCY``); resolving them one at a time
    was the largest fixed cost of a research iteration.
    """
    state.status = "retrieving"
    top_k = int(state.config.get("top_k", 5))
    org = state.organization_id

    # Queries not yet answered this run (we track them to bound work).
    executed = set(state.used_queries)
    pending = [q for q in state.search_queries if q not in executed]

    if not pending:
        return state

    # Every attempted query is recorded first, so a failing query is never
    # retried forever.
    state.used_queries.extend(pending)

    failed_any = False
    for query, result in zip(pending, _retrieve_pending(services, org, pending, top_k)):
        if result.failed:
            failed_any = True
            continue
        state.retrieved = _merge_unique(state.retrieved, result.chunks)
        # remember which queries produced nothing so the gap node can retry
        if not result.chunks:
            state.gaps.append(query)

    if failed_any:
        state.errors.append("A retrieval query failed; continuing.")

    # Trim to a sane cap so we never embed/analyze an unbounded set.
    state.retrieved = state.retrieved[: int(state.config.get("max_chunks", 300))]
    return state
