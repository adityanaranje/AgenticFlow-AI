"""Retriever node (Phase 5, §5/§7)."""

from __future__ import annotations

from app.agents.context import ResearchServices
from app.agents.state import ResearchState, RetrievedChunk


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


def retriever_node(state: ResearchState, services: ResearchServices) -> ResearchState:
    """Retrieve evidence for every open query, scoped to the organization.

    Retrieval is always filtered by ``organization_id`` (enforced inside
    ``services.retrieve`` → Phase 4 vector store), so the agent can never
    reach another tenant's chunks.
    """
    state.status = "retrieving"
    top_k = int(state.config.get("top_k", 5))
    org = state.organization_id

    # Queries not yet answered this run (we track them to bound work).
    executed = set(state.used_queries)
    pending = [q for q in state.search_queries if q not in executed]

    if not pending:
        return state

    for query in pending:
        state.used_queries.append(query)
        try:
            chunks = services.retrieve(org, query, top_k, {})
        except Exception:
            # A single query failing must not kill the run; log via state.
            state.errors.append("A retrieval query failed; continuing.")
            continue
        state.retrieved = _merge_unique(state.retrieved, chunks or [])
        # remember which queries produced nothing so the gap node can retry
        if not chunks:
            state.gaps.append(query)

    # Trim to a sane cap so we never embed/analyze an unbounded set.
    state.retrieved = state.retrieved[: int(state.config.get("max_chunks", 300))]
    return state
