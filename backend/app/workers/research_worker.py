"""Research background worker (Phase 5, §18).

Consumes research jobs from the Redis queue and runs the LangGraph-style
research pipeline (see :mod:`app.agents.research_graph`).

Run directly::

    python -m app.workers.research_worker
"""

from __future__ import annotations

from app.agents.research_graph import run_research, run_worker_loop
from app.core.logging import get_logger

logger = get_logger(__name__)


def process_research(research_id: str) -> dict:
    return run_research(research_id)


def main() -> None:
    run_worker_loop()


if __name__ == "__main__":
    main()
