"""Runtime collaborators injected into research node functions.

Nodes stay pure w.r.t. :class:`ResearchState` and talk to the outside world
only through this context, which makes them trivially unit-testable with
fakes and keeps dependency injection explicit (Phase 5, §26).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

from app.agents.state import ResearchState, RetrievedChunk


@dataclass
class ResearchServices:
    """Collaborators available to every research node."""

    # model call: returns raw assistant text for a message list
    llm: Callable[[list[dict[str, str]]], str]
    # tenant-scoped retrieval -> list of RetrievedChunk
    retrieve: Callable[
        [str, str, int, Optional[dict]], list[RetrievedChunk]
    ]
    # read the research question / config without blocking
    config: dict = field(default_factory=dict)

    def persist(self, state: ResearchState) -> None:
        """Hook the runner overrides to write progress to the DB."""
        return None

    def is_cancelled(self) -> bool:
        return False


def default_config() -> dict:
    """Sensible research defaults (values overridable per-run from config)."""
    from app.core.config import settings

    return {
        "top_k": 5,
        "max_subquestions": 5,
        "max_iterations": int(settings.max_research_iterations),
        "model": settings.openai_chat_model,
    }
