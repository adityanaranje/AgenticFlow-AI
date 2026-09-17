"""Research run orchestration (Phase 5, §2/§18).

Create a run, enqueue it onto Redis, return immediately. Processing happens in
the research worker (``python -m app.workers.research_worker``) that consumes
that queue.

Two fallbacks keep a run from waiting forever:

* Redis unavailable — the run is dispatched to the shared in-process
  background pool (:mod:`app.services.background`). It is never executed
  inline in the HTTP request, and one burst of questions cannot spawn
  unbounded threads.
* Redis available but nobody consuming the queue (a bare ``uvicorn`` dev
  setup, or a worker that is down) — after
  ``RESEARCH_UNCLAIMED_FALLBACK_SECONDS`` the API process claims the job back
  off the queue and runs it. The claim is an atomic ``LREM`` of the exact
  queue message, so a worker and the fallback can never both run a job.
"""

from __future__ import annotations

import threading
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger
from app.db.repositories.research import ResearchRepository
from app.services import background, job_queue, llm_guardrails

logger = get_logger(__name__)

# Input guardrail: the only per-run config keys clients may set, and the
# sane bounds they are clamped to. Unbounded values (huge top_k / chunk
# counts) would quietly multiply token spend, so they are capped here.
_CONFIG_BOUNDS = {
    "top_k": (1, 50),
    "max_subquestions": (1, 10),
    "max_iterations": (1, 5),
    "max_chunks": (1, 500),
}


def sanitize_research_config(config: dict | None) -> dict:
    """Return a safe per-run config: known numeric keys clamped to bounds.

    Unknown keys are dropped — clients cannot inject model names, budgets
    or anything else the platform does not explicitly allow.
    """
    safe: dict = {}
    for key, (low, high) in _CONFIG_BOUNDS.items():
        if config is None or key not in config:
            continue
        try:
            value = int(config[key])
        except (TypeError, ValueError):
            continue
        safe[key] = max(low, min(high, value))
    return safe


def _run_inline(research_id: str) -> None:
    """Execute a research run in the background pool."""
    from app.agents.research_graph import run_research

    run_research(research_id)


def _spawn_inline(research_id: str) -> None:
    background.submit(_run_inline, research_id)


def _schedule_unclaimed_check(research_id: str, delay: float) -> None:
    """Check back later whether a worker took the job (daemon timer)."""
    timer = threading.Timer(delay, _claim_unclaimed, args=(research_id, delay))
    timer.daemon = True
    timer.start()


def _claim_unclaimed(research_id: str, delay: float) -> None:
    """Run a research job in-process when no worker claimed it in time."""
    try:
        if ResearchRepository().get_status(research_id) != "queued":
            return  # a worker picked it up (or it already settled)
        if not job_queue.claim_research(research_id):
            return  # nothing left on the queue: a worker has it
        logger.warning(
            "No research worker claimed %s within %ss; running it in the API process.",
            research_id,
            int(delay),
        )
        _spawn_inline(research_id)
    except Exception:  # pragma: no cover - defensive, never kill the timer thread
        logger.exception("Could not take over the unclaimed research run %s.", research_id)


def create_research(
    *,
    organization_id: str,
    user_id: str,
    question: str,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a research run (status queued) and enqueue background execution.

    Usage guardrails (token quotas + concurrent-run limit) are enforced
    here; a rejected run is marked ``failed`` with the reason instead of
    being silently dropped. Raises :class:`AdmissionError` for the API to
    map to HTTP 429.
    """
    repo = ResearchRepository()
    run = repo.create(
        organization_id=organization_id,
        user_id=user_id,
        question=question.strip(),
        config=sanitize_research_config(config),
    )
    if not run:
        raise RuntimeError("Could not create the research run.")

    research_id = run["id"]
    try:
        llm_guardrails.admit_research_run(user_id, research_id)
    except Exception as exc:
        # The row must not linger as "queued" with nothing to process it.
        try:
            repo.update(
                research_id,
                organization_id,
                {"status": "failed", "error": str(exc)[:500]},
            )
        except Exception:
            logger.exception("Could not mark rejected run %s as failed.", research_id)
        raise

    if job_queue.enqueue_research(research_id):
        delay = settings.research_unclaimed_fallback_seconds
        if delay > 0:
            _schedule_unclaimed_check(research_id, float(delay))
        return run

    logger.info(
        "Redis unavailable; running research %s in the background pool.",
        research_id,
    )
    _spawn_inline(research_id)
    return run


def cancel_research(research_id: str, organization_id: str) -> bool:
    """Request cancellation (the worker stops at the next node boundary)."""
    repo = ResearchRepository()
    run = repo.get(research_id, organization_id)
    if not run:
        return False
    repo.update(
        research_id,
        organization_id,
        {"status": "cancelled"},
    )
    # A run cancelled before anything started it must not be executed later:
    # drop its pending queue message. This is a no-op when a worker already
    # popped the job (it then stops at the next node boundary).
    job_queue.claim_research(research_id)
    logger.info("Research %s cancelled.", research_id)
    return True
