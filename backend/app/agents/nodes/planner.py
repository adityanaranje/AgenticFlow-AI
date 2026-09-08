"""Planner node (Phase 5, §5/§6)."""

from __future__ import annotations

from app.agents import prompts
from app.agents.context import ResearchServices
from app.agents.llm import parse_json_object
from app.agents.state import ResearchState


def planner_node(state: ResearchState, services: ResearchServices) -> ResearchState:
    """Break the question into a bounded set of sub-questions + search queries."""
    state.status = "planning"
    max_sub = int(state.config.get("max_subquestions", 5))

    # Replace the placeholder token (do NOT use str.format: the prompt body
    # itself contains JSON braces).
    system = prompts.PLANNER_SYSTEM.replace("{max_subquestions}", str(max_sub))
    user = f'Research question:\n"{state.original_query}"'

    text = services.llm(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
    )

    try:
        payload = parse_json_object(text)
        sub_questions = [
            str(s).strip()
            for s in payload.get("sub_questions", [])
            if str(s).strip()
        ]
    except Exception:
        # Fall back to the original question so research can continue; the
        # runner never fabricates sub-questions beyond this.
        sub_questions = [state.original_query]

    # Bound the number of sub-questions (never unlimited).
    sub_questions = sub_questions[:max_sub] or [state.original_query]

    state.sub_questions = sub_questions
    # Search queries are derived from the sub-questions + original question.
    queries = [state.original_query] + list(sub_questions)
    state.search_queries = list(
        dict.fromkeys(q for q in queries if q.strip())
    )[: int(max_sub * 2)]
    return state
