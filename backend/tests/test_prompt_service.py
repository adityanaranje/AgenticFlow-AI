"""Prompt service tests: Langfuse retrieval + in-code fallback behaviour.

Langfuse is unconfigured in the test environment (see conftest), so the
fallback path runs by default; a fake client is injected to cover the
Langfuse path without any network.
"""

import pytest

from app.agents import prompts
from app.services import prompt_service


class _FakeTextPrompt:
    def __init__(self, rendered: str, seen: dict):
        self._rendered = rendered
        self._seen = seen

    def compile(self, **variables):
        self._seen["compile"].update(variables)
        return self._rendered


class _FakeClient:
    def __init__(self, rendered: str, error: Exception | None = None):
        self.rendered = rendered
        self.error = error
        self.calls: list[dict] = []
        self._seen: dict = {"compile": {}}

    def get_prompt(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return _FakeTextPrompt(self.rendered, self._seen)


def test_fallback_when_langfuse_unconfigured(monkeypatch):
    monkeypatch.setattr(prompt_service, "get_langfuse", lambda: None)

    text = prompt_service.get_system_prompt(
        "research-planner",
        fallback=prompts.PLANNER_SYSTEM,
        variables={"max_subquestions": 7},
    )

    assert "at most 7" in text
    assert "{{max_subquestions}}" not in text
    # JSON braces in the template survive untouched.
    assert '{"sub_questions": ["...", "..."]}' in text


def test_unknown_variable_left_intact_in_fallback():
    text = prompt_service._render_fallback(
        "limit is {{max_subquestions}} and {{unknown_var}}",
        {"max_subquestions": 3},
    )
    assert text == "limit is 3 and {{unknown_var}}"


def test_uses_langfuse_production_prompt(monkeypatch):
    client = _FakeClient("from-langfuse")
    monkeypatch.setattr(prompt_service, "get_langfuse", lambda: client)

    text = prompt_service.get_system_prompt(
        "research-planner",
        fallback=prompts.PLANNER_SYSTEM,
        variables={"max_subquestions": 5},
    )

    assert text == "from-langfuse"
    assert client.calls == [
        {
            "name": "research-planner",
            "type": "text",
            "label": "production",
            "cache_ttl_seconds": prompt_service.settings.prompt_cache_ttl_seconds,
        }
    ]
    assert client._seen["compile"] == {"max_subquestions": 5}


def test_falls_back_when_fetch_fails(monkeypatch, caplog):
    client = _FakeClient("unused", error=RuntimeError("prompt not found"))
    monkeypatch.setattr(prompt_service, "get_langfuse", lambda: client)

    text = prompt_service.get_system_prompt(
        "research-gap-detector",
        fallback=prompts.GAP_SYSTEM,
    )

    assert text == prompts.GAP_SYSTEM
    assert "Could not fetch Langfuse prompt" in caplog.text


def test_nodes_use_langfuse_prompt_end_to_end(monkeypatch):
    """Full pipeline with a Langfuse client: the fake LLM still sees the
    compiled system prompts, proving nodes route through the service."""
    from app.agents.context import ResearchServices
    from app.agents.nodes.planner import planner_node
    from app.agents.state import ResearchState
    import json

    client = _FakeClient("You are a research planner (langfuse v9).")
    monkeypatch.setattr(prompt_service, "get_langfuse", lambda: client)

    def fake_llm(messages):
        assert "langfuse v9" in messages[0]["content"]
        return json.dumps({"sub_questions": ["A"]})

    services = ResearchServices(
        llm=fake_llm, retrieve=lambda *a, **k: [], config={"max_subquestions": 5}
    )
    state = ResearchState(
        research_id="r",
        organization_id="org",
        user_id="u",
        original_query="q",
        config={"max_subquestions": 5},
    )
    state = planner_node(state, services)
    assert state.sub_questions == ["A"]
