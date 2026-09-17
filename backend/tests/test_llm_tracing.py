"""Tests: llm.chat() records Langfuse generations (model, I/O, tokens).

A fake OpenAI client + fake generation recorder stand in for the real
services, so this verifies the tracing wiring without any network.
"""

import pytest

from app.agents import llm


# --- fakes -----------------------------------------------------------------

class _FakeGeneration:
    def __init__(self):
        self.start_kwargs: dict = {}
        self.updates: list[dict] = []
        self.ended = False

    def update(self, **kwargs):
        self.updates.append(kwargs)

    def end(self):
        self.ended = True


def _install_fake_generation(monkeypatch, store: dict) -> None:
    def fake_llm_generation(name, **kwargs):
        gen = _FakeGeneration()
        gen.start_kwargs = {"name": name, **kwargs}
        store["gen"] = gen
        return gen

    monkeypatch.setattr(llm, "llm_generation", fake_llm_generation)


class _FakeCompletions:
    def __init__(self, parent):
        self._parent = parent

    def create(self, **kwargs):
        return self._parent._create(**kwargs)


class _FakeChat:
    def __init__(self, parent):
        self.completions = _FakeCompletions(parent)


class _FakeOpenAI:
    """Mimics ``openai.OpenAI`` just far enough for ``chat()``."""

    def __init__(self, raise_error: Exception | None = None):
        self.raise_error = raise_error
        self.seen: dict = {}
        self.chat = _FakeChat(self)

    def _create(self, **kwargs):
        self.seen = kwargs
        if self.raise_error is not None:
            raise self.raise_error

        class _Obj:
            pass

        message = _Obj()
        message.content = "hello world"
        choice = _Obj()
        choice.message = message
        usage = _Obj()
        usage.prompt_tokens = 11
        usage.completion_tokens = 7
        response = _Obj()
        response.choices = [choice]
        response.usage = usage
        return response


def _fake_client(monkeypatch, fake: _FakeOpenAI) -> None:
    monkeypatch.setattr(llm, "get_openai_client", lambda: fake)


_MESSAGES = [{"role": "user", "content": "hi"}]


# --- tests ------------------------------------------------------------------

def test_chat_records_generation_with_model_input_output_usage(monkeypatch):
    store: dict = {}
    _install_fake_generation(monkeypatch, store)
    fake = _FakeOpenAI()
    _fake_client(monkeypatch, fake)

    text = llm.chat(_MESSAGES, temperature=0.2, max_tokens=123)

    assert text == "hello world"
    gen = store["gen"]

    # start: name, model, full messages, parameters
    assert gen.start_kwargs["name"] == "openai.chat"
    assert gen.start_kwargs["model"] == llm.settings.openai_chat_model
    assert gen.start_kwargs["input_data"] == _MESSAGES
    assert gen.start_kwargs["metadata"] == {"temperature": 0.2, "max_tokens": 123}

    # completion: output + token usage (SDK input/output/total keys)
    final = [u for u in gen.updates if "output" in u]
    assert final, "generation must be updated with the model output"
    assert final[-1]["output"] == "hello world"
    assert final[-1]["usage_details"] == {"input": 11, "output": 7, "total": 18}
    assert gen.ended


def test_chat_failure_marks_generation_error(monkeypatch):
    store: dict = {}
    _install_fake_generation(monkeypatch, store)
    _fake_client(monkeypatch, _FakeOpenAI(raise_error=RuntimeError("boom")))

    with pytest.raises(llm.ResearchLLMError):
        llm.chat(_MESSAGES)

    gen = store["gen"]
    assert {"level": "error"} in gen.updates
    assert gen.ended


def test_chat_without_langfuse_still_works(monkeypatch):
    """No Langfuse configured (conftest) → llm_generation already returns a
    no-op; chat() must not change behaviour."""
    _fake_client(monkeypatch, _FakeOpenAI())

    assert llm.chat(_MESSAGES) == "hello world"
