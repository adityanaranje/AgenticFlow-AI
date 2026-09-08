"""Gap detector node (Phase 5, §5/§9).

Decides whether the gathered evidence is sufficient. When it is not (and the
iteration budget allows), it produces targeted follow-up search queries so the
runner can loop back to the retriever. Retries are bounded by the configurable
``max_iterations``.
"""

from __future__ import annotations

from app.agents import prompts
from app.agents.context import ResearchServices
from app.agents.llm import parse_json_object
from app.agents.state import ResearchState


def _evidence_coverage(state: ResearchState) -> bool:
    # A run with real retrieved evidence is treated as sufficient; empty
    # retrieval must trigger a bounded retry with fresh queries.
    return len(state.retrieved) >= 1


def gap_detector_node(state: ResearchState, services: ResearchServices) -> ResearchState:
    """Evaluate sufficiency and record gaps / follow-up queries."""
    state.status = "checking_gaps"

    sufficient = _evidence_coverage(state)
    follow_up: list[str] = []
    gaps: list[str] = []

    if not state.retrieved:
        gaps.append("No relevant documents were found for the question.")
        # Derive a targeted follow-up from unanswered sub-questions.
        answered = set(state.used_queries)
        follow_up = [
            q for q in state.sub_questions if q not in answered
        ] or [state.original_query]
    else:
        try:
            text = services.llm(
                [
                    {"role": "system", "content": prompts.GAP_SYSTEM},
                    {
                        "role": "user",
                        "content": (
                            f"Question: {state.original_query}\n"
                            f"Claims gathered: {len(state.evidence)}\n"
                            f"Retrieved chunks: {len(state.retrieved)}\n"
                            f"Prior gaps: {state.gaps[:5]}\n"
                        ),
                    },
                ]
            )
            payload = parse_json_object(text)
            sufficient = bool(payload.get("sufficient", _evidence_coverage(state)))
            gaps = [str(g) for g in payload.get("gaps", []) if str(g).strip()]
            follow_up = [
                str(q) for q in payload.get("follow_up_queries", []) if str(q).strip()
            ]
        except Exception:
            sufficient = _evidence_coverage(state)

    state.gaps = list(dict.fromkeys(state.gaps + gaps))
    # Bound and store the queries the runner should try next (if any).
    max_iter = int(state.config.get("max_iterations", 3))
    state.search_queries = (
        list(dict.fromkeys(follow_up))[: max_iter * 2] if not sufficient else []
    )
    return state
