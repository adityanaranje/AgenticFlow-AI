"""Research background worker (Phase 5, §18).

Consumes research jobs from the Redis queue and runs the LangGraph-style
research pipeline (see :mod:`app.agents.research_graph`). Research runs stay in
``queued`` state until this process consumes them.

Run directly::

    python -m app.workers.research_worker

Ctrl+C and ``SIGTERM`` (``docker stop``) stop the consumer threads once the run
they are executing finishes.
"""

from __future__ import annotations

from app.agents.research_graph import _STOP, run_research, run_worker_loop
from app.core.logging import get_logger

logger = get_logger(__name__)


def process_research(research_id: str) -> dict:
    return run_research(research_id)


def _install_signal_handlers(stop) -> None:
    """Stop the loops on Ctrl+C / SIGTERM instead of being killed mid-run."""
    import signal

    def _handle(signum, _frame):  # pragma: no cover - signal delivery
        logger.info("Research worker received signal %s; finishing current run.", signum)
        stop.set()

    for name in ("SIGINT", "SIGTERM"):
        sig = getattr(signal, name, None)
        if sig is None:
            continue
        try:
            signal.signal(sig, _handle)
        except (ValueError, OSError):  # pragma: no cover - non-main thread
            return


def main() -> None:
    _install_signal_handlers(_STOP)
    run_worker_loop()


if __name__ == "__main__":
    main()
