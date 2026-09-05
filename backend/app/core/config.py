import os
from functools import lru_cache
from dotenv import load_dotenv

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()

class Settings(BaseSettings):
    # Application

    model_config = SettingsConfigDict(
        env_file = ".env",
        env_file_encoding = "utf-8",
        case_sensitive=True,
        extra="ignore",
    )


    environment: str = Field(default="development", alias="ENVIRONMENT")
    app_name: str = Field(default="AgentFlow AI", alias="APP_NAME")
    api_host: str = Field(default="0.0.0.0", alias="API_HOST")
    api_port: int = Field(default="8000", alias="API_PORT")

    frontend_url: str = Field(default="http://localhost:3000", alias="FRONTEND_URL")

    # OpenAI
    openai_api_key : str = Field(default = "",alias = "OPENAI_API_KEY")
    openai_chat_model: str = Field(default = "",alias = "OPENAI_CHAT_MODEL")
    openai_embedding_model: str = Field(default = "text-embedding-3-small",alias = "OPENAI_EMBEDDING_MODEL")

    # Supabase
    supabase_url: str = Field(default = "",alias = "SUPABASE_URL")
    supabase_service_role_key: str = Field(default = "",alias = "SUPABASE_SERVICE_ROLE_KEY")
    supabase_publishable_key: str = Field(default = "",alias = "SUPABASE_PUBLISHABLE_KEY")

    # Qdrant
    qdrant_url: str = Field(default = "",alias = "QDRANT_URL")
    qdrant_api_key: str = Field(default = "",alias = "QDRANT_API_KEY")
    qdrant_collection: str = Field(default = "agentflow_documents",alias = "QDRANT_COLLECTION")


    # Redis
    redis_url: str = Field(default = "",alias = "REDIS_URL")
    redis_ttl_seconds: int = Field(default = 3600,alias = "REDIS_TTL_SECONDS")

    llm_cache_enabled: bool = Field( default=True, alias="LLM_CACHE_ENABLED", ) 
    semantic_cache_enabled: bool = Field( default=True, alias="SEMANTIC_CACHE_ENABLED", ) 
    embedding_cache_enabled: bool = Field( default=True, alias="EMBEDDING_CACHE_ENABLED", ) 
    retrieval_cache_enabled: bool = Field( default=True, alias="RETRIEVAL_CACHE_ENABLED", ) 
    web_search_cache_enabled: bool = Field( default=True, alias="WEB_SEARCH_CACHE_ENABLED", )


    # Langfuse
    langfuse_public_key: str = Field(default = "",alias = "LANGFUSE_PUBLIC_KEY")
    langfuse_secret_key: str = Field(default = "",alias = "LANGFUSE_SECRET_KEY")
    langfuse_base_url: str = Field(default = "https://cloud.langfuse.com",alias = "LANGFUSE_BASE_URL")

    # MCP
    mcp_host: str = Field(default = "0.0.0.0",alias = "MCP_HOST")
    mcp_port: int = Field(default = "8001",alias = "MCP_PORT")
    mcp_url: str = Field(default = "http://localhost:8001/mcp",alias = "MCP_URL")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached application settings."""
    return Settings()

settings = get_settings()