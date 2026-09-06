from contextlib import asynccontextmanager

from app.api.auth import router as auth_router
from app.api.documents import router as documents_router
from app.api.evaluations import router as evaluations_router
from app.api.health import health_root_router
from app.api.health import router as health_router
from app.api.organizations import router as organizations_router
from app.api.reports import router as reports_router
from app.api.research import router as research_router
from app.core.config import settings
from app.core.langfuse import flush_langfuse
from app.core.logging import configure_logging, get_logger
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle: startup and clean shutdown hooks."""
    configure_logging()

    logger.info(
        "Starting AgentFlow AI backend (environment=%s, version=%s)",
        settings.environment,
        settings.app_version,
    )

    yield

    logger.info("Shutting down AgentFlow AI backend.")
    flush_langfuse()
    logger.info("Langfuse flushed. Shutdown complete.")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "Production-oriented multi-agent AI research and knowledge "
        "intelligence platform."
    ),
    lifespan=lifespan,
)

# CORS: the Next.js frontend talks to this API from the browser.
# Backend-only secrets (service-role key, Langfuse secret, Qdrant key)
# are never exposed through CORS headers or API payloads.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Versioned application API prefix: /api/v1
app.include_router(health_router)
app.include_router(auth_router)
app.include_router(organizations_router)
app.include_router(documents_router)
app.include_router(research_router)
app.include_router(reports_router)
app.include_router(evaluations_router)

# Root-level health endpoint (also available at /api/v1/health).
app.include_router(health_root_router)


@app.get("/", tags=["meta"])
def root() -> dict[str, str]:
    """Basic API information."""
    return {
        "name": settings.app_name,
        "status": "running",
        "version": settings.app_version,
    }
