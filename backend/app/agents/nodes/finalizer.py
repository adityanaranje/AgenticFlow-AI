"""Finalizer node (Phase 5, §5/§12)."""

from __future__ import annotations

import re

from app.agents.context import ResearchServices
from app.agents.state import ReportSection, ResearchState


def _parse_sections(markdown: str) -> list[ReportSection]:
    headings = list(re.finditer(r"^#\s+(.+)$", markdown, flags=re.M))
    sections: list[ReportSection] = []
    for i, match in enumerate(headings):
        start = match.end()
        end = headings[i + 1].start() if i + 1 < len(headings) else len(markdown)
        body = markdown[start:end].strip()
        sections.append(ReportSection(heading=match.group(1).strip(), body=body))
    return sections


def _compute_confidence(state: ResearchState) -> float | None:
    scores = [ev.confidence for ev in state.evidence if ev.confidence]
    if not scores:
        return None
    # Combine average confidence with citation/evidence breadth, capped in [0,1].
    coverage = min(1.0, len(state.evidence) / max(1, len(state.retrieved)))
    mean = sum(scores) / len(scores)
    return round(max(0.0, min(1.0, 0.7 * mean + 0.3 * coverage)), 4)


def finalizer_node(state: ResearchState, services: ResearchServices) -> ResearchState:
    """Assemble the final report, its sections and an overall confidence."""
    final = (state.draft or "").strip()

    # Fallback: if synthesis produced nothing, build a minimal grounded
    # report from evidence so we never emit an empty report.
    if not final:
        lines = ["# Executive Summary", "", "# Research Question", "", state.original_query]
        lines += ["", "# Evidence"]
        for ev in state.evidence:
            lines.append(f"- {ev.claim}  [{ev.filename or 'document'}]")
        final = "\n".join(lines)

    state.final_report = final
    state.sections = _parse_sections(final)
    state.confidence = _compute_confidence(state)
    state.status = "completed"
    return state
