"""Supabase-backed authentication & membership authorization (Phase 3, §15).

The FastAPI backend never trusts a ``user_id`` or ``organization_id`` supplied
by the client. Every privileged endpoint instead:

1. ``get_current_user`` — verifies the caller's Supabase access token
   (sent as ``Authorization: Bearer <jwt>``) against Supabase Auth and
   returns the authenticated user derived from the token.
2. ``require_organization_membership`` — confirms a real membership row
   exists in ``organization_members`` for that user in the organization,
   and returns the membership (role) instead of trusting the caller.
3. Role enforcement is layered on top in :mod:`app.core.rbac`.

No service-role key is ever exposed; the service-role client here is only
used server-side to read the membership table (the caller's own JWT is what
proves who they are).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from fastapi import Depends, HTTPException, Path, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.exceptions import ConfigurationError
from app.core.logging import get_logger
from app.db.supabase import get_supabase

logger = get_logger(__name__)

# Canonical organization roles and their privilege ranking (higher = more).
# Mirrors the PostgreSQL role check constraint (owner/admin/researcher/viewer).
ROLE_RANK: dict[str, int] = {
    "owner": 4,
    "admin": 3,
    "researcher": 2,
    "viewer": 1,
}

_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AuthenticatedUser:
    """An identity proven by a validated Supabase access token."""

    id: str
    email: str | None = None
    user_metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Membership:
    """A validated membership of ``user`` in ``organization_id``."""

    user: AuthenticatedUser
    organization_id: str
    role: str


def _unauthorized(detail: str = "Not authenticated.") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _forbidden(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> AuthenticatedUser:
    """Validate the caller's Supabase access token and return the user.

    Reads ``Authorization: Bearer <jwt>`` and verifies it against Supabase
    Auth's ``/auth/v1/user`` endpoint. Never trusts a token's payload without
    verification.
    """
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _unauthorized("Missing bearer token.")

    token = credentials.credentials
    client = get_supabase()

    if client is None:
        raise ConfigurationError(
            "Supabase is not configured; cannot authenticate requests."
        ) from None

    try:
        response = client.auth.get_user(token)
    except Exception:  # invalid/expired/malformed token, network failure
        logger.debug("Supabase token verification failed.", exc_info=True)
        raise _unauthorized("Invalid or expired access token.") from None

    user = getattr(response, "user", None)

    if user is None:
        raise _unauthorized("Access token did not resolve to a user.")

    return AuthenticatedUser(
        id=str(user.id),
        email=getattr(user, "email", None),
        user_metadata=getattr(user, "user_metadata", {}) or {},
    )


def _fetch_membership_role(organization_id: str, user_id: str) -> str | None:
    """Return the caller's role in an organization, or ``None``.

    Queries the membership table server-side so the browser can never assert
    membership on its own.
    """
    client = get_supabase()

    if client is None:
        logger.warning("Supabase is not configured; membership check skipped.")
        return None

    try:
        response = (
            client.table("organization_members")
            .select("role")
            .eq("organization_id", organization_id)
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )
    except Exception:
        logger.warning(
            "Membership lookup failed for org=%s", organization_id, exc_info=True
        )
        return None

    data = response.data
    if not data:
        return None
    role = data.get("role")
    return str(role) if role else None


def get_membership_for(
    user: AuthenticatedUser,
    organization_id: str,
) -> Membership | None:
    """Resolve a user's membership in an org, or ``None`` if not a member.

    Organization ids supplied by the client are validated here against the
    membership table — never trusted blindly.
    """
    role = _fetch_membership_role(organization_id, user.id)

    if role is None:
        return None

    return Membership(user=user, organization_id=organization_id, role=role)


def require_organization_membership(
    organization_id: str = Path(..., description="Organization to authorize against"),
    user: AuthenticatedUser = Depends(get_current_user),
) -> Membership:
    """Require that ``user`` is a member of ``organization_id``.

    Raises 403 when the user is not a member (non-members must not receive
    any tenant data). Organization ids supplied by the client are validated
    here, never trusted blindly.
    """
    membership = get_membership_for(user, organization_id)

    if membership is None:
        raise _forbidden("You are not a member of this organization.")

    return membership


def require_role(
    minimum_role: str,
) -> Callable[..., Membership]:
    """Return a dependency enforcing ``minimum_role`` or higher.

    Uses the membership already validated by
    :func:`require_organization_membership`. ``minimum_role`` must be a
    canonical organization role (owner/admin/researcher/viewer).
    """
    min_rank = ROLE_RANK.get(minimum_role, 0)

    def dependency(
        membership: Membership = Depends(require_organization_membership),
    ) -> Membership:
        actual_rank = ROLE_RANK.get(membership.role, 0)
        if actual_rank < min_rank:
            raise _forbidden(
                f"Requires the '{minimum_role}' role or higher "
                f"(your role is '{membership.role}')."
            )
        return membership

    return dependency
