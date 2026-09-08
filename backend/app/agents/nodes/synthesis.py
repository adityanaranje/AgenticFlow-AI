"""Synthesis node (Phase 5, §5/§10)."""

from __future__ import annotations

from app.agents import prompts
from app.agents.context import ResearchServices
from app.agents.state import ResearchState


def synthesis_node(state: ResearchState, services: ResearchServices) -> ResearchState:
    """Generate a grounded Markdown report from the validated evidence."""
    state.status = "synthesizing"

    evidence_lines = []
    for i, ev in enumerate(state.evidence):
        evidence_lines.append(
            f"[E{i}] (source: {ev.supporting_source}, confidence {ev.confidence:.2f})\n"
            f"{ev.claim}\n\nVerbatim supporting excerpt:\n{ev.supporting_chunk[:1500]}"
        )

    user = (
        f"Research question:\n{state.original_query}\n\n"
        "Evidence (cite ONLY these, as [E<number>]):\n\n"
        + "\n\n".join(evidence_lines)
        + (
            "\n\nKnown gaps / missing information:\n"
            + "\n".join(f"- {g}" for g in state.gaps)
            if state.gaps
            else ""
        )
    )

    draft = services.llm(
        [
            {"role": "system", "content": prompts.SYNTHESIS_SYSTEM},
            {"role": "user", "content": user},
        ]
    )

    state.draft = draft
    return state
