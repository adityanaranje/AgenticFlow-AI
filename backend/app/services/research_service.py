"""Research run orchestration (Phase 5, §2/§18).

Create a run, enqueue it onto Redis, return immediately. If Redis is
unavailable the run is dispatched to the shared in-process background pool
(:mod:`app.services.background`) — never executed inline — so the HTTP
request returns without waiting for a long-running model pipeline and one
burst of questions cannot spawn unbounded threads.
"""

from __future__ import annotations

from typing import Any

from app.core.logging import get_logger
from app.db.repositories.research import ResearchRepository
from app.services import background, job_queue

logger = get_logger(__name__)


def _run_inline(research_id: str) -> None:
    """Execute a research run in the background pool."""
    from app.agents.research_graph import run_research

    run_research(research_id)


def _spawn_inline(research_id: str) -> None:
    background.submit(_run_inline, research_id)


def create_research(
    *,
    organization_id: str,
    user_id: str,
    question: str,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a research run (status queued) and enqueue background execution."""
    repo = ResearchRepository()
    run = repo.create(
        organization_id=organization_id,
        user_id=user_id,
        question=question.strip(),
        config=config or {},
    )
    if not run:
        raise RuntimeError("Could not create the research run.")

    research_id = run["id"]
    if not job_queue.enqueue_research(research_id):
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
    return True
