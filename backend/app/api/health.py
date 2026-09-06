from app.api.schemas import HealthResponse
from app.services.health_service import get_system_health
from fastapi import APIRouter

# Canonical versioned endpoint: GET /api/v1/health
router = APIRouter(
    prefix="/api/v1",
    tags=["health"],
)


@router.get("/health", response_model=HealthResponse)
def health() -> dict:
    """Return application and external-service health."""
    return get_system_health()


# Unversioned convenience endpoint required by Phase 1: GET /health
health_root_router = APIRouter(
    tags=["health"],
)


@health_root_router.get("/health", response_model=HealthResponse)
def health_root() -> dict:
    """Alias of ``/api/v1/health`` kept for infrastructure probes."""
    return get_system_health()
