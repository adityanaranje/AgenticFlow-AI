from fastapi import APIRouter
from app.services.health_service import get_system_health

router = APIRouter(
    prefix="/api/v1",
    tags=["health"],
)

@router.get("/health")
def health() -> dict:
    """Return appplication and external-service health."""
    return get_system_health()