"""Research graph & runner (Phase 5, §5/§18/§23).

Nodes:
    planner → retriever → evidence_analyzer → gap_detector
        └── (insufficient & budget) → retriever …
    then synthesis → citation_validator → finalizer

``run_research(research_id)`` drives the deterministic engine for production
(Redis worker) with per-node progress + cancellation + safe failure handling.

``build_research_graph()`` additionally exposes the same nodes as a
LangGraph ``StateGraph`` for environments that want the compiled graph.

A run is a chain of dependent model calls, so its latency is bounded by how
much of the independent work runs at once and how tight each provider call
is:

    - every open query is retrieved together: one embeddings request plus
      concurrent vector searches, instead of one round trip per query;
    - retrieved chunks are analysed in parallel batches that each fit the
      model's context window;
    - mid-run progress writes carry only the counters/queries the UI needs,
      and cancellation checks read just the status column — neither pulls the
      multi-megabyte full state over the wire after every node;
    - ``RESEARCH_WORKER_CONCURRENCY`` runs execute in parallel, so several
      research questions do not queue behind one another.
"""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Any

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
from app.core.observability import current_observation, user_scope
from app.db.repositories.research import ResearchRepository
from app.services import background, job_queue, report_service, retrieval

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


def _to_chunk(row: dict[str, Any]) -> RetrievedChunk:
    """Map one retrieval row onto the agent's chunk type."""
    return RetrievedChunk(
        document_id=str(row.get("document_id") or ""),
        chunk_id=str(row.get("chunk_id") or ""),
        content=str(row.get("content") or ""),
        filename=str(row.get("filename") or ""),
        page_number=row.get("page_number"),
        chunk_index=row.get("chunk_index"),
        score=float(row.get("score") or 0.0),
        metadata=dict(row.get("metadata") or {}),
    )


def _default_retrieve(
    organization_id: str, query: str, top_k: int, filters=None
) -> list[RetrievedChunk]:
    rows = retrieval.retrieve_context(
        organization_id=organization_id,
        query=query,
        top_k=top_k,
        filters=filters,
    )
    return [_to_chunk(row) for row in rows or []]


def _default_retrieve_many(
    organization_id: str, queries: list[str], top_k: int, filters=None
) -> list[list[RetrievedChunk]]:
    """Batch retrieval: one embeddings request, then concurrent searches."""
    rows_per_query = retrieval.retrieve_context_many(
        organization_id=organization_id,
        queries=list(queries),
        top_k=top_k,
        filters=filters,
    )
    return [[_to_chunk(row) for row in rows or []] for rows in rows_per_query]


def _default_llm(messages: list[dict[str, str]]) -> str:
    return llm_mod.chat(messages)


def _build_services(state: ResearchState, run_id: str, organization_id: str, repo: ResearchRepository) -> ResearchServices:
    """Services wired to the DB-backed persist/cancel for production runs."""

    def persist(s: ResearchState) -> None:
        # Progress writes stay small: the full state (chunks, evidence,
        # fragments of the report) can reach megabytes and is written once the
        # run reaches a terminal status.
        try:
            repo.update(
                run_id,
                organization_id,
                {
                    "status": s.status,
                    "graph_state": s.to_progress_jsonable(),
                    "error": None,
                },
            )
        except Exception:
            logger.exception("Failed to persist research progress for %s", run_id)

    def is_cancelled() -> bool:
        # Reads only the status column: fetching the whole row transferred the
        # full graph_state several times per run just to compare one string.
        try:
            return repo.get_status(run_id) == "cancelled"
        except Exception:
            return False

    services = ResearchServices(
        llm=_default_llm,
        retrieve=_default_retrieve,
        retrieve_many=_default_retrieve_many,
        config=state.config,
    )
    services.persist = persist
    services.is_cancelled = is_cancelled
    return services


def _evaluate_report_safely(organization_id: str, report_id: str, run_id: str) -> None:
    """Evaluate a stored report; never affects the research run itself."""
    try:
        from app.services.evaluation_service import evaluate_report

        evaluate_report(
            organization_id=organization_id,
            report_id=report_id,
            test_case=f"research:{run_id}",
        )
    except Exception:
        logger.exception("Automatic evaluation failed for research %s", run_id)


def run_research(research_id: str) -> dict[str, Any]:
    """Execute the full agentic research pipeline for one run id."""
    started = time.perf_counter()
    repo = ResearchRepository()
    run = repo.get_any(research_id)
    if run is None:
        raise ValueError(f"Research run {research_id} does not exist.")

    organization_id = run["organization_id"]
    config = dict(run.get("config") or {})

    if run.get("status") == "cancelled":
        # Cancelled while it was still queued: the job must not start now.
        logger.info("Research %s was cancelled before it started; skipping.", research_id)
        return {"status": "cancelled"}

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
        # One Langfuse trace per run, properly nested: every node span is
        # the *active* span inside its block (current_observation), so the
        # LLM generations recorded by app.agents.llm.chat attach under the
        # right node automatically. Node spans carry compact input/output
        # summaries; the full model I/O lives on the generations.
        run_meta = {"research_id": run["id"], "organization_id": organization_id}
        with user_scope(run.get("user_id")):
            with current_observation("research.run", metadata=run_meta):
                # ---- planner ----
                with current_observation("research.planner", metadata={"research_id": run["id"]}) as span:
                    state = planner_node(state, services)
                    span.update(
                        input={"question": state.original_query},
                        output={
                            "sub_questions": state.sub_questions,
                            "search_queries": state.search_queries,
                        },
                    )
                services.persist(state)

                # ---- retrieval → analysis → gap loop (bounded) ----
                iteration = 0
                while iteration <= max_iter:
                    state.iteration = iteration
                    if services.is_cancelled():
                        _cancel(repo, run["id"], organization_id, state)
                        return {"status": "cancelled"}

                    with current_observation(
                        "research.retrieve",
                        metadata={"research_id": run["id"], "queries": len(state.search_queries)},
                    ) as span:
                        state = retriever_node(state, services)
                        span.update(
                            input={"queries": state.search_queries},
                            output={"retrieved_chunks": len(state.retrieved)},
                        )
                    services.persist(state)
                    if services.is_cancelled():
                        _cancel(repo, run["id"], organization_id, state)
                        return {"status": "cancelled"}

                    with current_observation(
                        "research.evidence",
                        metadata={"research_id": run["id"], "retrieved": len(state.retrieved)},
                    ) as span:
                        state = evidence_analyzer_node(state, services)
                        span.update(
                            input={"chunks_analysed": len(state.retrieved)},
                            output={"claims": len(state.evidence)},
                        )
                    services.persist(state)

                    with current_observation(
                        "research.gap",
                        metadata={"research_id": run["id"], "iteration": iteration},
                    ) as span:
                        state = gap_detector_node(state, services)
                        span.update(
                            input={
                                "claims": len(state.evidence),
                                "retrieved_chunks": len(state.retrieved),
                                "iteration": iteration,
                            },
                            output={
                                "sufficient": not state.search_queries,
                                "gaps": state.gaps[-5:],
                                "follow_up_queries": state.search_queries,
                            },
                        )
                    services.persist(state)

                    if state.search_queries and iteration < max_iter:
                        iteration += 1
                        continue
                    break

                if services.is_cancelled():
                    _cancel(repo, run["id"], organization_id, state)
                    return {"status": "cancelled"}

                # ---- synthesis / validation / finalize ----
                with current_observation("research.synthesis", metadata={"research_id": run["id"]}) as span:
                    state = synthesis_node(state, services)
                    span.update(
                        input={"evidence_items": len(state.evidence)},
                        output={"report_chars": len(state.draft or "")},
                    )
                services.persist(state)

                with current_observation(
                    "research.citations",
                    metadata={"research_id": run["id"], "evidence": len(state.evidence)},
                ) as span:
                    state = citation_validator_node(state, services)
                    span.update(
                        input={"evidence_items": len(state.evidence)},
                        output={"citations": len(state.citations)},
                    )
                services.persist(state)

                with current_observation("research.finalize", metadata={"research_id": run["id"]}) as span:
                    state = finalizer_node(state, services)
                    span.update(
                        output={
                            "sections": len(state.sections),
                            "confidence": state.confidence,
                        }
                    )

        # ---- store the report + sources ----
        stored = report_service.store_report(state)
        if stored is None:
            raise RuntimeError("Report could not be stored.")

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
            "Research %s completed (%d chunks, %d citations) in %.2fs.",
            run["id"],
            len(state.retrieved),
            len(state.citations),
            time.perf_counter() - started,
        )

        # Auto-evaluate the produced report (it never modifies the report).
        # Scoring costs another model call, so it runs *after* the run is
        # marked completed: the report is already available and the
        # evaluation must not delay it. Failures never affect the run.
        background.submit(
            _evaluate_report_safely,
            organization_id,
            stored["id"],
            run["id"],
        )
        return {"status": "completed", "report_id": stored.get("id")}

    except Exception as exc:
        logger.exception("Research %s failed", run["id"])
        safe = (str(exc) or "Research failed.").strip().replace("\n", " ")[:1000]
        state.status = "failed"  # keep the persisted state consistent with the row
        try:
            repo.update(
                run["id"],
                organization_id,
                {
                    "status": "failed",
                    "error": safe or "Research failed.",
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    # Terminal write: persist what was gathered so a failed
                    # run is still inspectable (mid-run writes are summaries).
                    "graph_state": state.to_jsonable(),
                },
            )
        except Exception:
            logger.exception("Failed to record research failure for %s", run["id"])
        return {"status": "failed", "error": safe}


def _cancel(repo, run_id, org, state) -> None:
    state.status = "cancelled"  # keep the persisted state consistent with the row
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


# Set by SIGINT/SIGTERM (see :mod:`app.workers.research_worker`) or by tests to
# stop the consumer threads: each thread finishes the run it is executing and
# exits instead of popping another job, so a container stop is graceful.
_STOP = threading.Event()


def _consume_forever(
    worker_id: int, wait: int, stop_event: threading.Event | None = None
) -> None:
    """Pop and execute research runs until the process is stopped."""
    stop = stop_event if stop_event is not None else _STOP
    while not stop.is_set():
        research_id = job_queue.pop_with_backoff(job_queue.pop_next_research, wait)
        if not research_id:
            continue
        try:
            run_research(research_id)
        except Exception:
            logger.exception(
                "Unhandled research worker error for %s (thread %d)",
                research_id,
                worker_id,
            )


def run_worker_loop(
    interval: int | None = None,
    concurrency: int | None = None,
    stop_event: threading.Event | None = None,
) -> None:
    """Blocking research worker consumer.

    ``concurrency`` runs execute in parallel (each is a chain of network-bound
    model and vector calls), so a second question does not wait for the first
    to finish. Jobs are popped from the shared Redis list, which
    load-balances naturally. Setting ``stop_event`` (or signalling the
    process) stops the threads once their current run finishes.
    """
    wait = interval if interval is not None else settings.research_worker_poll_seconds
    # A blocking BLPOP must return before the Redis client's socket read
    # timeout (3s) fires, otherwise every idle poll raises a socket timeout.
    wait = max(1, min(int(wait), 3))
    workers = max(1, int(concurrency or settings.research_worker_concurrency))

    logger.info(
        "Research worker started (queue=%s, threads=%d, poll=%ss).",
        job_queue.RESEARCH_QUEUE,
        workers,
        wait,
    )

    stop = stop_event if stop_event is not None else _STOP
    threads = [
        threading.Thread(
            target=_consume_forever,
            args=(index, wait, stop),
            name=f"research-worker-{index}",
            daemon=True,
        )
        for index in range(workers)
    ]
    for thread in threads:
        thread.start()

    try:
        for thread in threads:
            thread.join()
    except KeyboardInterrupt:  # pragma: no cover - interactive stop
        logger.info("Research worker interrupted; shutting down.")
        stop.set()
