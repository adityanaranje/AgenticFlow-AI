import inspect
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
from app.core.cors import build_cors_config, describe_cors_config
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

    # Log what the CORS middleware will actually accept. A browser origin that
    # is missing from this list is the reason an OPTIONS preflight (e.g. the
    # document upload) comes back 400 "Disallowed CORS origin".
    logger.info("CORS allowlist: %s", describe_cors_config(_cors))

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

# CORS: the Next.js frontend talks to this API from the browser, so every
# non-simple request (a multipart document upload, an Authorization header)
# is preceded by an OPTIONS preflight. An origin that is not allowlisted
# makes Starlette answer that preflight with 400 "Disallowed CORS origin" —
# the browser then reports the POST as a CORS failure. The allowlist is
# therefore built (and validated) in app.core.cors, from FRONTEND_URL (a
# comma-separated list, normalised the way browsers send an Origin) plus an
# optional FRONTEND_ORIGIN_REGEX.
#
# Backend-only secrets (service-role key, Langfuse secret, Qdrant key)
# are never exposed through CORS headers or API payloads.
_cors = build_cors_config(
    frontend_url=settings.frontend_url,
    origin_regex=settings.frontend_origin_regex,
    environment=settings.environment,
    allow_private_network=settings.cors_allow_private_network,
)

_cors_kwargs: dict = {
    "allow_origins": _cors.allow_origins,
    "allow_origin_regex": _cors.allow_origin_regex,
    "allow_credentials": True,
    "allow_methods": ["*"],
    "allow_headers": ["*"],
}
# ``allow_private_network`` only exists in Starlette >= 0.47; skip it on an
# older pin instead of failing to boot.
if "allow_private_network" in inspect.signature(CORSMiddleware).parameters:
    _cors_kwargs["allow_private_network"] = _cors.allow_private_network

app.add_middleware(CORSMiddleware, **_cors_kwargs)

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
