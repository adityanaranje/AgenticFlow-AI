"""Authentication routes (Phase 1 placeholder).

Frontend authentication is handled by Supabase Auth directly
(password flow + PKCE callback). Backend auth endpoints
(session verification, JWT scopes, API keys) are introduced in a
later phase; this router exists so the API surface is registered
under ``/api/v1`` from day one.
"""

from fastapi import APIRouter

router = APIRouter(
    prefix="/api/v1/auth",
    tags=["auth"],
)
