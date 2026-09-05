from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.core.config import settings
from app.core.langfuse import flush_langfuse
from app.core.logging import configure_logging

@asynccontextmanager
async def lifespan(_:FastAPI):
    """Applicatino lifecycle."""

    configure_logging()

    yield

    flush_langfuse()

app = FastAPI(
    title=settings.app_name,
    version = "0.1.0",
    description=(
        "Production-oriented multi-agent AI research "
        "and knowledge intelligence platform."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=[""],
)

app.include_router(health_router)

@app.get("/")
def root() -> dict[str, str]:
    """Basic API information."""
    return {
        "name": settings.app_name,
        "status":"running",
        "version":"0.1.0",
    }