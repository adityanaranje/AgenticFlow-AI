"""Research run orchestration (Phase 5, §2/§18).

Create a run, enqueue it onto Redis, return immediately. If Redis is
unavailable we fall back to a daemon thread so the HTTP request still returns
without blocking on a long-running model pipeline.
"""

from __future__ import annotations

import threading
from typing import Any

from app.core.logging import get_logger
from app.db.repositories.research import ResearchRepository
from app.services import job_queue

logger = get_logger(__name__)


def _spawn_inline(research_id: str) -> None:
    def _run() -> None:
        try:
            from app.agents.research_graph import run_research

            run_research(research_id)
        except Exception:
            logger.exception("Inline research execution failed for %s", research_id)

    thread = threading.Thread(target=_run, name=f"research-{research_id[:8]}", daemon=True)
    thread.start()


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
        logger.warning("Redis unavailable; running research %s inline.", research_id)
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
