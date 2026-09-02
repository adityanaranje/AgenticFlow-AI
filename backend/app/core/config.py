import os
from functools import lru_cache
from dotenv import load_dotenv

from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()

class Settings(BaseSettings):
    # Application
    environment: str = os.getenv("ENVIRONMENT")
    app_name: str = os.getenv("APP_NAME")
    api_host: str = os.getenv("API_HOST")
    api_port: int = os.getenv("API_PORT")
    frontend_url: str = os.getenv("FRONTEND_URL")

    # OpenAI
    openai_api_key : str = os.getenv("OPENAI_API_KEY")
    openai_chat_model: str = os.getenv("OPENAI_CHAT_MODEL")
    openai_embedding_model: str = os.getenv("OPENAI_EMBEDDING_MODEL")

    # Supabase
    supabase_url: str = os.getenv("SUPABASE_URL")
    supabase_service_role_key: str = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    supabase_publishable_key: str = os.getenv("SUPABASE_PUBLISHABLE_KEY")

    # Qdrant
    qdrant_url: str = os.getenv("QDRANT_URL")
    qdrant_api_key: str = os.getenv("QDRANT_API_KEY")
    qdrant_collection: str = os.getenv("QDRANT_COLLECTION")

    # Langfuse
    langfuse_public_key: str = os.getenv("LANGFUSE_PUBLIC_KEY")
    langfuse_secret_key: str = os.getenv("LANGFUSE_SECRET_KEY")
    langfuse_base_url: str = os.getenv("LANGFUSE_BASE_URL")

    # MCP
    mcp_host: str = os.getenv("MCP_HOST")
    mcp_port: int = os.getenv("MCP_PORT")
    mcp_url: str = os.getenv("MCP_URL")

    model_config = SettingsConfigDict(
        env_file = ".env",
        env_file_encoding = "utf-8",
        case_sensitive=False,
        extra="ignore",
    )

@lru_cache
def get_settings() -> Settings:
    return Settings()

settings = get_settings()