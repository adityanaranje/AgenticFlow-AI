from pydantic import BaseModel, Field


class ServiceHealth(BaseModel):
    status: str
    detail: str | None = None


class HealthResponse(BaseModel):
    status: str
    openai: ServiceHealth
    supabase: ServiceHealth
    qdrant: ServiceHealth
    redis: ServiceHealth
    langfuse: ServiceHealth


# ----------------------------------------------------------------------
# Organization membership (Phase 3, §16)
# ----------------------------------------------------------------------


class InviteMemberRequest(BaseModel):
    """Invite somebody to an organization by email.

    ``role`` is validated against the canonical role list server-side in
    :mod:`app.services.membership`; only an owner may request ``owner``.
    """

    email: str = Field(..., max_length=320, description="Invitee email address")
    role: str = Field("viewer", description="owner | admin | researcher | viewer")


class UpdateMemberRoleRequest(BaseModel):
    """Change an existing member's role."""

    role: str = Field(..., description="owner | admin | researcher | viewer")
