"""Backend role-based access control (Phase 3, §16).

Thin layer over :mod:`app.core.auth` that turns "membership was validated"
into role-specific authorization. Every dependency first requires a validated
membership (``require_organization_membership``) and then enforces the role.

Role hierarchy: viewer < researcher < admin < owner.

Only the FastAPI dependency functions below are meant to be used in routes:

    from fastapi import Depends
    from app.core.rbac import require_viewer, require_researcher

    @router.get("/{organization_id}/research")
    def run_research(
        membership=Depends(require_researcher()),
    ):
        ...
"""

from __future__ import annotations

from typing import Callable

from app.core.auth import (
    ROLE_RANK,
    Membership,
    require_organization_membership,
    require_role,
)

# Named canonical roles (shared single source of truth).
ROLE_OWNER = "owner"
ROLE_ADMIN = "admin"
ROLE_RESEARCHER = "researcher"
ROLE_VIEWER = "viewer"

# The hierarchy, most privileged first.
ROLE_HIERARCHY: tuple[str, ...] = (
    ROLE_OWNER,
    ROLE_ADMIN,
    ROLE_RESEARCHER,
    ROLE_VIEWER,
)

__all__ = [
    "ROLE_OWNER",
    "ROLE_ADMIN",
    "ROLE_RESEARCHER",
    "ROLE_VIEWER",
    "ROLE_HIERARCHY",
    "ROLE_RANK",
    "has_minimum_role",
    "require_viewer",
    "require_researcher",
    "require_admin",
    "require_owner",
    "require_organization_membership",
    "Membership",
]


def has_minimum_role(actual_role: str | None, required_role: str) -> bool:
    """Pure predicate: is ``actual_role`` at or above ``required_role``?"""
    if not actual_role:
        return False
    return ROLE_RANK.get(actual_role, 0) >= ROLE_RANK.get(required_role, 0)


# Dependencies that also enforce a minimum role on top of membership.
def require_viewer() -> Callable[..., Membership]:
    """Any member of the organization (viewer+)."""
    return require_role(ROLE_VIEWER)


def require_researcher() -> Callable[..., Membership]:
    """Researcher or above (can run research / contribute documents)."""
    return require_role(ROLE_RESEARCHER)


def require_admin() -> Callable[..., Membership]:
    """Admin or owner (can manage organization & members)."""
    return require_role(ROLE_ADMIN)


def require_owner() -> Callable[..., Membership]:
    """Only the owner (can delete the organization)."""
    return require_role(ROLE_OWNER)
