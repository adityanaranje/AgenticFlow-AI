"""Organization routes (Phase 1 placeholder).

Endpoints for creating and managing organizations and memberships
are implemented in a later phase on top of the multi-tenant data
model (see ``database/migrations/003_organizations.sql``).
"""

from fastapi import APIRouter

router = APIRouter(
    prefix="/api/v1/organizations",
    tags=["organizations"],
)
