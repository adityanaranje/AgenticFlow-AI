"""Finalizer node (Phase 5, §5/§12)."""

from __future__ import annotations

import re

from app.agents.context import ResearchServices
from app.agents.state import ReportSection, ResearchState
from app.core.config import settings


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


def _cap_report_length(markdown: str) -> str:
    """Output guardrail: bound the stored report to RESEARCH_MAX_REPORT_CHARS.

    Truncates at a line boundary so we never cut mid-sentence, and records a
    visible marker so readers know the report was capped rather than complete.
    """
    limit = max(0, int(settings.research_max_report_chars))
    if limit <= 0 or len(markdown) <= limit:
        return markdown
    cut = markdown.rfind("\n", 0, limit)
    if cut < limit // 2:  # no sensible line boundary; hard-cut instead
        cut = limit
    return (
        markdown[:cut].rstrip()
        + "\n\n> _Note: report truncated to the configured length limit "
        f"({limit:,} characters)._"
    )


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

    state.final_report = _cap_report_length(final)
    state.sections = _parse_sections(state.final_report)
    state.confidence = _compute_confidence(state)
    state.status = "completed"
    return state
