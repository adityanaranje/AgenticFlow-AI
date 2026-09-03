from pydantic import BaseModel

class ServiceHealth(BaseModel):
    status: str
    detail: str | None = None


class HealthResponse(BaseModel):
    status: str
    openai: ServiceHealth
    supabase: ServiceHealth
    qdrant: ServiceHealth
    langfuse: ServiceHealth