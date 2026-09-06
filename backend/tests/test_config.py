"""Configuration-loading tests.

The application settings are a module-level singleton, so these
tests instantiate fresh ``Settings`` objects against a controlled
environment instead of mutating the shared one.
"""

import importlib

import pytest
from app.core.config import Settings, settings
from pydantic import ValidationError


def test_defaults_are_development_safe():
    assert settings.environment == "development"
    assert settings.app_name == "AgentFlow AI"
    assert settings.api_v1_prefix == "/api/v1"
    assert settings.qdrant_collection == "agentflow_documents"
    assert settings.redis_ttl_seconds == 3600
    assert settings.api_host == "0.0.0.0"
    assert settings.api_port == 8000


def test_secrets_default_to_empty_strings():
    """Secrets must never be hard-coded; empty defaults are expected."""
    assert settings.openai_api_key == ""
    assert settings.supabase_url == ""
    assert settings.supabase_service_role_key == ""
    assert settings.qdrant_url == ""
    assert settings.qdrant_api_key == ""
    assert settings.redis_url == ""
    assert settings.langfuse_public_key == ""
    assert settings.langfuse_secret_key == ""


def test_env_aliases_from_os_environment(monkeypatch):
    """Phase-1 names (OPENAI_MODEL / LANGFUSE_HOST) must be honoured."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4o-mini")
    monkeypatch.setenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("QDRANT_URL", "https://qdrant.example.com")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("LANGFUSE_HOST", "https://langfuse.example.com")

    fresh = Settings(_env_file=None)

    assert fresh.openai_api_key == "sk-test-not-a-real-key"
    assert fresh.openai_chat_model == "gpt-4o-mini"
    assert fresh.openai_model == "gpt-4o-mini"
    assert fresh.openai_embedding_model == "text-embedding-3-small"
    assert fresh.langfuse_host == "https://langfuse.example.com"
    assert fresh.langfuse_base_url == "https://langfuse.example.com"
    assert fresh.is_production is False


def test_legacy_names_still_work(monkeypatch):
    """Legacy scaffolding names must keep working as fallbacks."""
    monkeypatch.setenv("OPENAI_CHAT_MODEL", "gpt-4.1-mini")
    monkeypatch.setenv("LANGFUSE_BASE_URL", "https://eu.langfuse.example.com")

    fresh = Settings(_env_file=None)

    assert fresh.openai_chat_model == "gpt-4.1-mini"
    assert fresh.openai_model == "gpt-4.1-mini"
    assert fresh.langfuse_host == "https://eu.langfuse.example.com"
    assert fresh.langfuse_base_url == "https://eu.langfuse.example.com"


def test_explicit_values_beat_aliases(monkeypatch):
    monkeypatch.setenv("OPENAI_MODEL", "alias-value")
    monkeypatch.setenv("OPENAI_CHAT_MODEL", "explicit-value")

    fresh = Settings(_env_file=None)

    assert fresh.openai_model == "explicit-value"


def test_invalid_port_raises(monkeypatch):
    monkeypatch.setenv("API_PORT", "not-a-number")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_config_module_imports():
    """Settings and the cached getter are importable."""
    importlib.import_module("app.core.config")

    from app.core.config import get_settings

    assert get_settings() is get_settings()
