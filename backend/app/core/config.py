import os
from functools import lru_cache

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()


class Settings(BaseSettings):
    """Centralized application configuration.

    All environment variables are read from the process environment and/or
    the ``.env`` file located at the repository root (backend/.env when the
    backend runs from its own directory). Secrets are never hard-coded and
    never shipped to the browser: the backend-only keys
    (``SUPABASE_SERVICE_ROLE_KEY``, ``LANGFUSE_SECRET_KEY``,
    ``QDRANT_API_KEY``, ``OPENAI_API_KEY``) must only be consumed
    server-side.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # Application
    environment: str = Field(default="development", alias="ENVIRONMENT")
    app_name: str = Field(default="AgentFlow AI", alias="APP_NAME")
    app_version: str = Field(default="0.1.0", alias="APP_VERSION")
    api_host: str = Field(default="0.0.0.0", alias="API_HOST")
    api_port: int = Field(default=8000, alias="API_PORT")
    api_v1_prefix: str = Field(default="/api/v1", alias="API_V1_PREFIX")

    frontend_url: str = Field(default="http://localhost:3000", alias="FRONTEND_URL")

    # OpenAI
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    openai_chat_model: str = Field(default="gpt-4o-mini", alias="OPENAI_CHAT_MODEL")
    openai_embedding_model: str = Field(
        default="text-embedding-3-small", alias="OPENAI_EMBEDDING_MODEL"
    )

    # Supabase
    supabase_url: str = Field(default="", alias="SUPABASE_URL")
    supabase_anon_key: str = Field(default="", alias="SUPABASE_ANON_KEY")
    supabase_service_role_key: str = Field(default="", alias="SUPABASE_SERVICE_ROLE_KEY")

    # Qdrant
    qdrant_url: str = Field(default="", alias="QDRANT_URL")
    qdrant_api_key: str = Field(default="", alias="QDRANT_API_KEY")
    qdrant_collection: str = Field(
        default="agentflow_documents", alias="QDRANT_COLLECTION"
    )

    # Redis
    redis_url: str = Field(default="", alias="REDIS_URL")
    redis_ttl_seconds: int = Field(default=3600, alias="REDIS_TTL_SECONDS")

    llm_cache_enabled: bool = Field(default=True, alias="LLM_CACHE_ENABLED")
    semantic_cache_enabled: bool = Field(default=True, alias="SEMANTIC_CACHE_ENABLED")
    embedding_cache_enabled: bool = Field(default=True, alias="EMBEDDING_CACHE_ENABLED")
    retrieval_cache_enabled: bool = Field(default=True, alias="RETRIEVAL_CACHE_ENABLED")
    web_search_cache_enabled: bool = Field(default=True, alias="WEB_SEARCH_CACHE_ENABLED")

    # Langfuse
    langfuse_public_key: str = Field(default="", alias="LANGFUSE_PUBLIC_KEY")
    langfuse_secret_key: str = Field(default="", alias="LANGFUSE_SECRET_KEY")
    langfuse_host: str = Field(default="https://cloud.langfuse.com", alias="LANGFUSE_HOST")

    # MCP
    mcp_host: str = Field(default="0.0.0.0", alias="MCP_HOST")
    mcp_port: int = Field(default=8001, alias="MCP_PORT")
    mcp_url: str = Field(default="http://localhost:8001/mcp", alias="MCP_URL")

    def __init__(self, **values: object) -> None:
        """Apply Phase-1 environment aliases.

        Phase 1 declares ``OPENAI_MODEL`` / ``LANGFUSE_HOST`` while early
        scaffolding used ``OPENAI_CHAT_MODEL`` / ``LANGFUSE_BASE_URL``.
        Prefer the Phase-1 canonical names and fall back to the legacy
        names when only those are present.
        """
        env = os.environ

        if "OPENAI_MODEL" in env and "OPENAI_CHAT_MODEL" not in env:
            values.setdefault("OPENAI_CHAT_MODEL", env["OPENAI_MODEL"])
        elif "OPENAI_CHAT_MODEL" in env and "OPENAI_MODEL" not in env:
            values.setdefault("OPENAI_MODEL", env["OPENAI_CHAT_MODEL"])

        if "LANGFUSE_HOST" in env and "LANGFUSE_BASE_URL" not in env:
            values.setdefault("LANGFUSE_BASE_URL", env["LANGFUSE_HOST"])
        elif "LANGFUSE_BASE_URL" in env and "LANGFUSE_HOST" not in env:
            values.setdefault("LANGFUSE_HOST", env["LANGFUSE_BASE_URL"])

        super().__init__(**values)

    @property
    def openai_model(self) -> str:
        """Canonical model name (``OPENAI_MODEL``, alias of ``OPENAI_CHAT_MODEL``)."""
        return self.openai_chat_model

    @property
    def langfuse_base_url(self) -> str:
        """Canonical Langfuse host URL (alias of ``LANGFUSE_HOST``)."""
        return self.langfuse_host

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"

    def require_secret(self, name: str) -> str | None:
        """Return the value of a secret-style setting if present, else ``None``."""
        value = getattr(self, name, "") or ""
        return value or None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached application settings."""
    return Settings()


settings = get_settings()
