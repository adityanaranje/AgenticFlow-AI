"""Prompt service tests: Langfuse retrieval + in-code fallback behaviour.

Langfuse is unconfigured in the test environment (see conftest), so the
fallback path runs by default; a fake client is injected to cover the
Langfuse path without any network.
"""

from app.agents import prompts
from app.core import observability
from app.services import prompt_service


class _FakeTextPrompt:
    def __init__(self, rendered: str, seen: dict):
        self._rendered = rendered
        self._seen = seen
        self.name = "research-planner"
        self.version = 9

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

    result = prompt_service.get_system_prompt(
        "research-planner",
        fallback=prompts.PLANNER_SYSTEM,
        variables={"max_subquestions": 7},
    )

    assert result.name == "research-planner"
    assert "at most 7" in result.text
    assert "{{max_subquestions}}" not in result.text
    assert result.client is None  # fallbacks are never linked to traces
    # JSON braces in the template survive untouched.
    assert '{"sub_questions": ["...", "..."]}' in result.text


def test_unknown_variable_left_intact_in_fallback():
    text = prompt_service._render_fallback(
        "limit is {{max_subquestions}} and {{unknown_var}}",
        {"max_subquestions": 3},
    )
    assert text == "limit is 3 and {{unknown_var}}"


def test_uses_langfuse_production_prompt(monkeypatch):
    client = _FakeClient("from-langfuse")
    monkeypatch.setattr(prompt_service, "get_langfuse", lambda: client)

    result = prompt_service.get_system_prompt(
        "research-planner",
        fallback=prompts.PLANNER_SYSTEM,
        variables={"max_subquestions": 5},
    )

    assert result.text == "from-langfuse"
    # The PromptClient is exposed so prompt_scope can link it to traces.
    assert result.client is not None
    assert result.version == 9
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

    result = prompt_service.get_system_prompt(
        "research-gap-detector",
        fallback=prompts.GAP_SYSTEM,
    )

    assert result.text == prompts.GAP_SYSTEM
    assert result.client is None
    assert "Could not fetch Langfuse prompt" in caplog.text


def test_prompt_scope_links_client_via_propagate_attributes(monkeypatch):
    """prompt_scope passes the PromptClient to propagate_attributes so the
    generations inside the scope carry the prompt name/version in traces."""
    events: list = []

    class _FakeCM:
        def __enter__(self):
            events.append("enter")
            return self

        def __exit__(self, *_args):
            events.append("exit")
            return False

    def fake_propagate(**kwargs):
        events.append(kwargs)
        return _FakeCM()

    monkeypatch.setattr(observability, "_propagate_attributes", lambda: fake_propagate)

    fake_client = object()
    prompt = prompt_service.ManagedPrompt(name="x", text="t", client=fake_client)
    with observability.prompt_scope(prompt) as linked:
        assert linked is fake_client

    assert {"prompt": fake_client} in events
    assert events.count("enter") == 1 and events.count("exit") == 1


def test_prompt_scope_is_noop_for_fallback_prompt():
    prompt = prompt_service.ManagedPrompt(name="x", text="t", client=None)
    with observability.prompt_scope(prompt) as linked:
        assert linked is None


def test_user_scope_propagates_user_id(monkeypatch):
    events: list = []

    class _FakeCM:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    def fake_propagate(**kwargs):
        events.append(kwargs)
        return _FakeCM()

    monkeypatch.setattr(observability, "_propagate_attributes", lambda: fake_propagate)
    with observability.user_scope("u-123"):
        pass
    assert {"user_id": "u-123"} in events

    events.clear()
    with observability.user_scope(None):
        pass
    assert events == []  # nothing to propagate


def test_nodes_use_langfuse_prompt_end_to_end(monkeypatch):
    """Full planner path with a Langfuse client: the fake LLM sees the
    compiled system prompt, proving nodes route through the service."""
    import json

    from app.agents.context import ResearchServices
    from app.agents.nodes.planner import planner_node
    from app.agents.state import ResearchState

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
