"""Research graph & runner (Phase 5, §5/§18/§23).

Nodes:
    planner → retriever → evidence_analyzer → gap_detector
        └── (insufficient & budget) → retriever …
    then synthesis → citation_validator → finalizer

``run_research(research_id)`` drives the deterministic engine for production
(Redis worker) with per-node progress + cancellation + safe failure handling.

``build_research_graph()`` additionally exposes the same nodes as a
LangGraph ``StateGraph`` for environments that want the compiled graph.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from app.agents import context as ctx_mod
from app.agents import llm as llm_mod
from app.agents import prompts  # noqa: F401  (prompt surface)
from app.agents.context import ResearchServices
from app.agents.nodes.citation_validator import citation_validator_node
from app.agents.nodes.evidence_analyzer import evidence_analyzer_node
from app.agents.nodes.finalizer import finalizer_node
from app.agents.nodes.gap_detector import gap_detector_node
from app.agents.nodes.planner import planner_node
from app.agents.nodes.retriever import retriever_node
from app.agents.nodes.synthesis import synthesis_node
from app.agents.state import ResearchState, RetrievedChunk
from app.core.config import settings
from app.core.logging import get_logger
from app.core.observability import ingestion_span
from app.db.repositories.research import ResearchRepository
from app.services import job_queue, report_service, retrieval

logger = get_logger(__name__)

# node name -> status label persisted to the run
NODE_STATUS = {
    "planner": "planning",
    "retriever": "retrieving",
    "evidence_analyzer": "analyzing",
    "gap_detector": "checking_gaps",
    "synthesis": "synthesizing",
    "citation_validator": "validating",
}


def _default_retrieve(organization_id: str, query: str, top_k: int, filters=None) -> list[RetrievedChunk]:
    rows = retrieval.retrieve_context(
        organization_id=organization_id,
        query=query,
        top_k=top_k,
        filters=filters,
    )
    chunks: list[RetrievedChunk] = []
    for row in rows or []:
        chunks.append(
            RetrievedChunk(
                document_id=str(row.get("document_id") or ""),
                chunk_id=str(row.get("chunk_id") or ""),
                content=str(row.get("content") or ""),
                filename=str(row.get("filename") or ""),
                page_number=row.get("page_number"),
                chunk_index=row.get("chunk_index"),
                score=float(row.get("score") or 0.0),
                metadata=dict(row.get("metadata") or {}),
            )
        )
    return chunks


def _default_llm(messages: list[dict[str, str]]) -> str:
    return llm_mod.chat(messages)


def _build_services(state: ResearchState, run_id: str, organization_id: str, repo: ResearchRepository) -> ResearchServices:
    """Services wired to the DB-backed persist/cancel for production runs."""

    def persist(s: ResearchState) -> None:
        try:
            repo.update(
                run_id,
                organization_id,
                {
                    "status": s.status,
                    "graph_state": s.to_jsonable(),
                    "error": None,
                },
            )
        except Exception:
            logger.exception("Failed to persist research progress for %s", run_id)

    def is_cancelled() -> bool:
        try:
            run = repo.get_any(run_id)
            return bool(run and run.get("status") == "cancelled")
        except Exception:
            return False

    services = ResearchServices(
        llm=_default_llm,
        retrieve=_default_retrieve,
        config=state.config,
    )
    services.persist = persist
    services.is_cancelled = is_cancelled
    return services


def run_research(research_id: str) -> dict[str, Any]:
    """Execute the full agentic research pipeline for one run id."""
    repo = ResearchRepository()
    run = repo.get_any(research_id)
    if run is None:
        raise ValueError(f"Research run {research_id} does not exist.")

    organization_id = run["organization_id"]
    config = dict(run.get("config") or {})
    max_iter = int(config.get("max_iterations", settings.max_research_iterations))

    state = ResearchState(
        research_id=run["id"],
        organization_id=organization_id,
        user_id=run["user_id"],
        original_query=run["question"],
        config=config,
        status="queued",
    )

    services = _build_services(state, run["id"], organization_id, repo)

    repo.set_status(
        run["id"], organization_id, "planning", started_at=datetime.now(timezone.utc).isoformat()
    )

    try:
        with ingestion_span(
            "research.run", metadata={"research_id": run["id"], "organization_id": organization_id}
        ):
            # ---- planner ----
            with ingestion_span("research.planner", metadata={"research_id": run["id"]}):
                state = planner_node(state, services)
            services.persist(state)

            # ---- retrieval → analysis → gap loop (bounded) ----
            iteration = 0
            while iteration <= max_iter:
                state.iteration = iteration
                if services.is_cancelled():
                    _cancel(repo, run["id"], organization_id, state)
                    return {"status": "cancelled"}

                with ingestion_span("research.retrieve", metadata={"research_id": run["id"], "queries": len(state.search_queries)}):
                    state = retriever_node(state, services)
                services.persist(state)
                if services.is_cancelled():
                    _cancel(repo, run["id"], organization_id, state)
                    return {"status": "cancelled"}

                with ingestion_span("research.evidence", metadata={"research_id": run["id"], "retrieved": len(state.retrieved)}):
                    state = evidence_analyzer_node(state, services)
                services.persist(state)

                with ingestion_span("research.gap", metadata={"research_id": run["id"], "iteration": iteration}):
                    state = gap_detector_node(state, services)
                services.persist(state)

                if state.search_queries and iteration < max_iter:
                    iteration += 1
                    continue
                break

            if services.is_cancelled():
                _cancel(repo, run["id"], organization_id, state)
                return {"status": "cancelled"}

            # ---- synthesis / validation / finalize ----
            with ingestion_span("research.synthesis", metadata={"research_id": run["id"]}):
                state = synthesis_node(state, services)
            services.persist(state)

            with ingestion_span("research.citations", metadata={"research_id": run["id"], "evidence": len(state.evidence)}):
                state = citation_validator_node(state, services)
            services.persist(state)

            with ingestion_span("research.finalize", metadata={"research_id": run["id"]}):
                state = finalizer_node(state, services)

        # ---- store the report + sources ----
        stored = report_service.store_report(state)
        if stored is None:
            raise RuntimeError("Report could not be stored.")

        # Auto-evaluate the produced report (never modifies it). Failures here
        # must not fail the research run.
        try:
            from app.services.evaluation_service import evaluate_report

            evaluate_report(
                organization_id=organization_id,
                report_id=stored["id"],
                test_case=f"research:{run['id']}",
            )
        except Exception:
            logger.exception("Automatic evaluation failed for research %s", run["id"])

        repo.update(
            run["id"],
            organization_id,
            {
                "status": "completed",
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "error": None,
                "graph_state": state.to_jsonable(),
            },
        )
        logger.info(
            "Research %s completed (%d chunks, %d citations).",
            run["id"],
            len(state.retrieved),
            len(state.citations),
        )
        return {"status": "completed", "report_id": stored.get("id")}

    except Exception as exc:  # noqa: BLE001 - centralized safe handling
        logger.exception("Research %s failed", run["id"])
        safe = (str(exc) or "Research failed.").strip().replace("\n", " ")[:1000]
        try:
            repo.update(
                run["id"],
                organization_id,
                {
                    "status": "failed",
                    "error": safe or "Research failed.",
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                },
            )
        except Exception:  # noqa: BLE001
            logger.exception("Failed to record research failure for %s", run["id"])
        return {"status": "failed", "error": safe}


def _cancel(repo, run_id, org, state) -> None:
    try:
        repo.update(
            run_id, org, {"status": "cancelled", "graph_state": state.to_jsonable()}
        )
    except Exception:
        logger.exception("Failed to persist cancellation for %s", run_id)
    logger.info("Research %s cancelled.", run_id)


def build_research_graph():
    """Return a compiled LangGraph StateGraph mirroring the deterministic flow.

    Imported lazily so importing this module never requires langgraph.
    """
    from langgraph.graph import END, START, StateGraph

    builder = StateGraph(dict)

    builder.add_node("planner", planner_node)
    builder.add_node("retriever", retriever_node)
    builder.add_node("evidence_analyzer", evidence_analyzer_node)
    builder.add_node("gap_detector", gap_detector_node)
    builder.add_node("synthesis", synthesis_node)
    builder.add_node("citation_validator", citation_validator_node)
    builder.add_node("finalizer", finalizer_node)

    builder.add_edge(START, "planner")
    builder.add_edge("planner", "retriever")
    builder.add_edge("retriever", "evidence_analyzer")
    builder.add_edge("evidence_analyzer", "gap_detector")

    def route_after_gap(state: dict) -> str:
        if isinstance(state, ResearchState):
            has_followup = bool(state.search_queries) and state.iteration < int(
                state.config.get("max_iterations", 3)
            )
            return "retriever" if has_followup else "synthesis"
        # dict channel representation
        qs = state.get("search_queries") or []
        return "retriever" if qs else "synthesis"

    builder.add_conditional_edges(
        "gap_detector", route_after_gap, {"retriever": "retriever", "synthesis": "synthesis"}
    )
    builder.add_edge("synthesis", "citation_validator")
    builder.add_edge("citation_validator", "finalizer")
    builder.add_edge("finalizer", END)

    return builder.compile()


def run_worker_loop(interval: Optional[int] = None) -> None:
    """Blocking research worker consumer."""
    wait = interval if interval is not None else 5
    logger.info("Research worker started (queue=%s).", job_queue.RESEARCH_QUEUE)
    while True:
        research_id = job_queue.pop_next_research(timeout=wait)
        if not research_id:
            continue
        try:
            run_research(research_id)
        except Exception:
            logger.exception("Unhandled research worker error for %s", research_id)
