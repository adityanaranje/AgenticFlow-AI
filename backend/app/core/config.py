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

    # Qdrant embedding collection shape
    embedding_dimensions: int = Field(
        default=1536, alias="EMBEDDING_DIMENSIONS"
    )

    # Document ingestion (text-embedding-3-small → 1536 dims; must match
    # the configured embedding model. See QDRANT_COLLECTION.)
    storage_bucket: str = Field(default="documents", alias="STORAGE_BUCKET")
    max_upload_size_mb: int = Field(default=25, alias="MAX_UPLOAD_SIZE_MB")

    # Chunking (character based, approximate). Configurable, never
    # hard-coded magic numbers.
    chunk_size: int = Field(default=1500, alias="CHUNK_SIZE")
    chunk_overlap: int = Field(default=200, alias="CHUNK_OVERLAP")

    # Ingestion throughput. Remote calls dominate ingestion time, so every
    # stage that talks to Supabase / OpenAI / Qdrant is batched and run with
    # a bounded amount of concurrency. All values are tunable per
    # deployment; sane defaults keep a single document fast without
    # exceeding provider rate limits.
    #
    # Embeddings: how many chunk texts go into one OpenAI request, and how
    # many requests run at once. (text-embedding-3-* accepts up to 2048
    # inputs per request; 256 keeps a request well under the token cap.)
    embedding_batch_size: int = Field(default=256, alias="EMBEDDING_BATCH_SIZE")
    embedding_concurrency: int = Field(default=4, alias="EMBEDDING_CONCURRENCY")
    embedding_max_retries: int = Field(default=3, alias="EMBEDDING_MAX_RETRIES")

    # Chunk rows: rows per ``document_chunks`` insert (one HTTP request per
    # batch instead of one per chunk) and batches in flight.
    chunk_insert_batch_size: int = Field(default=200, alias="CHUNK_INSERT_BATCH_SIZE")
    chunk_insert_concurrency: int = Field(default=2, alias="CHUNK_INSERT_CONCURRENCY")

    # Qdrant: points per upsert request (Qdrant recommends <= 100-200) and
    # how many upsert requests run at once.
    qdrant_upsert_batch_size: int = Field(default=128, alias="QDRANT_UPSERT_BATCH_SIZE")
    qdrant_upsert_concurrency: int = Field(default=2, alias="QDRANT_UPSERT_CONCURRENCY")

    # Document worker / job queue
    document_job_queue: str = Field(
        default="agentflow:documents:jobs", alias="DOCUMENT_JOB_QUEUE"
    )
    # Documents processed in parallel. One OCR-free ingestion job is
    # I/O-bound (embeddings + remote writes), so a handful of concurrent
    # documents keeps the queue draining when several files are uploaded.
    document_worker_concurrency: int = Field(
        default=4, alias="DOCUMENT_WORKER_CONCURRENCY"
    )
    # Idle BLPOP wait for the worker. Must stay below the Redis client's
    # socket timeout (3s) so an empty queue returns ``None`` cleanly
    # instead of raising a socket timeout on every poll.
    document_worker_poll_seconds: int = Field(
        default=2, alias="DOCUMENT_WORKER_POLL_SECONDS"
    )
    # When Redis is unavailable, processing falls back to an in-process
    # thread pool so upload requests still return immediately.
    inline_processing_workers: int = Field(default=2, alias="INLINE_PROCESSING_WORKERS")

    # Research worker / job queue
    research_job_queue: str = Field(
        default="agentflow:research:jobs", alias="RESEARCH_JOB_QUEUE"
    )

    # Research throughput. A run is a chain of dependent model calls, so the
    # wins come from doing independent work at once (retrieval for every open
    # query, evidence analysis over batches of chunks), from bounding each
    # provider call, and from not rewriting the run's whole state to the
    # database after every node.
    #
    # OpenAI per-request timeout, in seconds. The SDK default is 600s, which
    # turns a single stalled connection into a ten-minute "research is slow".
    openai_timeout_seconds: int = Field(default=60, alias="OPENAI_TIMEOUT_SECONDS")
    # Retries for transient research model errors (rate limits / timeouts).
    research_llm_max_retries: int = Field(
        default=2, alias="RESEARCH_LLM_MAX_RETRIES"
    )
    # Queries retrieved concurrently: each is one embedding + one vector
    # search, so the planner's sub-questions resolve together.
    retrieval_concurrency: int = Field(default=4, alias="RETRIEVAL_CONCURRENCY")
    # Evidence analysis is map-reduced over batches of retrieved chunks so a
    # single prompt cannot exceed the model's context window (and so the
    # batches can be analysed in parallel). The default keeps a typical run
    # (5 queries x 5 chunks, ~35k characters) in ONE prompt — identical to the
    # previous behaviour and cost — and only splits once the corpus of
    # excerpts grows past what a model handles reliably.
    evidence_batch_chars: int = Field(default=60000, alias="EVIDENCE_BATCH_CHARS")
    evidence_concurrency: int = Field(default=4, alias="EVIDENCE_CONCURRENCY")
    evidence_max_chunks: int = Field(default=48, alias="EVIDENCE_MAX_CHUNKS")
    # Research runs processed in parallel per worker process.
    research_worker_concurrency: int = Field(
        default=2, alias="RESEARCH_WORKER_CONCURRENCY"
    )
    research_worker_poll_seconds: int = Field(
        default=2, alias="RESEARCH_WORKER_POLL_SECONDS"
    )
    # If a queued run is still sitting on the queue this many seconds later,
    # no worker is consuming it (bare `uvicorn` dev setup, or a worker that is
    # down) and the API process takes the job over so the run does not wait
    # forever. The takeover is an atomic queue claim, so a job can never run
    # twice. Set to 0 to disable and require a worker always.
    research_unclaimed_fallback_seconds: int = Field(
        default=15, alias="RESEARCH_UNCLAIMED_FALLBACK_SECONDS"
    )
    # Rows per ``report_sources`` insert, and bulk inserts for chunk rows /
    # report sources in flight.
    report_source_batch_size: int = Field(
        default=100, alias="REPORT_SOURCE_BATCH_SIZE"
    )
    # Query-embedding cache (identical query text -> identical vector).
    embedding_cache_ttl_seconds: int = Field(
        default=3600, alias="EMBEDDING_CACHE_TTL_SECONDS"
    )

    # Research agent tuning
    max_research_iterations: int = Field(
        default=3, alias="MAX_RESEARCH_ITERATIONS"
    )
    research_timeout_seconds: int = Field(
        default=600, alias="RESEARCH_TIMEOUT_SECONDS"
    )
    default_research_top_k: int = Field(default=5, alias="RESEARCH_TOP_K")

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
