"""Organization + membership + invitation persistence.

All writes go through the Supabase service-role client, so the *only*
authorization boundary reached here is the database guard trigger
(`organization_members_guard`, migration 015). Callers must therefore
enforce RBAC before calling into this repository — the API layer does so
via :mod:`app.core.rbac`, and :mod:`app.services.membership` re-checks the
business invariants (last owner, self-demotion, rank) in Python so users
get clean error messages instead of raw Postgres exceptions.
"""

from typing import Any

from app.db.repositories import first_row
from app.db.supabase import get_supabase

# Columns selected for a member row, including the joined profile.
_MEMBER_SELECT = """
    id,
    organization_id,
    user_id,
    role,
    created_at,
    updated_at,
    profiles (
        id,
        full_name,
        avatar_url
    )
"""

_INVITATION_SELECT = """
    id,
    organization_id,
    email,
    role,
    status,
    invited_by,
    accepted_by,
    accepted_at,
    expires_at,
    created_at,
    updated_at
"""


class OrganizationRepository:
    """Repository for organization operations."""

    # ------------------------------------------------------------------
    # Organizations
    # ------------------------------------------------------------------

    def create(self, name: str, slug: str) -> dict[str, Any] | None:
        client = get_supabase()

        if client is None:
            return None

        response = client.rpc(
            "create_organization",
            {
                "organization_name": name,
                "organization_slug": slug,
            },
        ).execute()

        return response.data

    def get_for_user(self, user_id: str) -> list[dict[str, Any]]:
        client = get_supabase()

        if client is None:
            return []

        response = (
            client.table("organization_members")
            .select(
                """
                organization_id,
                role,
                organizations (
                    id,
                    name,
                    slug,
                    created_by,
                    created_at,
                    updated_at
                )
                """
            )
            .eq("user_id", user_id)
            .execute()
        )
        return response.data or []

    # ------------------------------------------------------------------
    # Members
    # ------------------------------------------------------------------

    def get_member(self, organization_id: str) -> list[dict[str, Any]]:
        """List every member of an organization (with their profile)."""
        client = get_supabase()

        if client is None:
            return []

        response = (
            client.table("organization_members")
            .select(_MEMBER_SELECT)
            .eq("organization_id", organization_id)
            .order("created_at")
            .execute()
        )

        return response.data or []

    def get_membership(
        self,
        organization_id: str,
        user_id: str,
    ) -> dict[str, Any] | None:
        """Return a single membership row, or ``None`` when absent."""
        client = get_supabase()

        if client is None:
            return None

        response = (
            client.table("organization_members")
            .select(_MEMBER_SELECT)
            .eq("organization_id", organization_id)
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )

        return first_row(response.data)

    def count_owners(self, organization_id: str) -> int:
        """How many owners the organization currently has."""
        client = get_supabase()

        if client is None:
            return 0

        response = (
            client.table("organization_members")
            .select("id")
            .eq("organization_id", organization_id)
            .eq("role", "owner")
            .execute()
        )

        return len(response.data or [])

    def add_member(
        self,
        organization_id: str,
        user_id: str,
        role: str,
    ) -> dict[str, Any] | None:
        """Insert a membership row directly (used when the user exists)."""
        client = get_supabase()

        if client is None:
            return None

        response = (
            client.table("organization_members")
            .insert(
                {
                    "organization_id": organization_id,
                    "user_id": user_id,
                    "role": role,
                }
            )
            .execute()
        )

        return first_row(response.data)

    def update_member_role(
        self,
        organization_id: str,
        user_id: str,
        role: str,
    ) -> dict[str, Any] | None:
        client = get_supabase()

        if client is None:
            return None

        response = (
            client.table("organization_members")
            .update({"role": role})
            .eq("organization_id", organization_id)
            .eq("user_id", user_id)
            .execute()
        )

        return first_row(response.data)

    def remove_member(self, organization_id: str, user_id: str) -> bool:
        client = get_supabase()

        if client is None:
            return False

        response = (
            client.table("organization_members")
            .delete()
            .eq("organization_id", organization_id)
            .eq("user_id", user_id)
            .execute()
        )

        return bool(response.data)

    # ------------------------------------------------------------------
    # Invitations
    # ------------------------------------------------------------------

    def list_invitations(
        self,
        organization_id: str,
        status: str | None = "pending",
    ) -> list[dict[str, Any]]:
        client = get_supabase()

        if client is None:
            return []

        query = (
            client.table("organization_invitations")
            .select(_INVITATION_SELECT)
            .eq("organization_id", organization_id)
        )

        if status:
            query = query.eq("status", status)

        response = query.order("created_at", desc=True).execute()

        return response.data or []

    def get_pending_invitation(
        self,
        organization_id: str,
        email: str,
    ) -> dict[str, Any] | None:
        client = get_supabase()

        if client is None:
            return None

        response = (
            client.table("organization_invitations")
            .select(_INVITATION_SELECT)
            .eq("organization_id", organization_id)
            .eq("email", email.strip().lower())
            .eq("status", "pending")
            .limit(1)
            .execute()
        )

        return first_row(response.data)

    def create_invitation(
        self,
        organization_id: str,
        email: str,
        role: str,
        invited_by: str,
    ) -> dict[str, Any] | None:
        """Create a pending invitation; the token is generated by Postgres."""
        client = get_supabase()

        if client is None:
            return None

        response = (
            client.table("organization_invitations")
            .insert(
                {
                    "organization_id": organization_id,
                    "email": email.strip().lower(),
                    "role": role,
                    "invited_by": invited_by,
                }
            )
            .execute()
        )

        return first_row(response.data)

    def get_invitation(self, invitation_id: str) -> dict[str, Any] | None:
        client = get_supabase()

        if client is None:
            return None

        response = (
            client.table("organization_invitations")
            .select(_INVITATION_SELECT + ", token")
            .eq("id", invitation_id)
            .limit(1)
            .execute()
        )

        return first_row(response.data)

    def revoke_invitation(self, invitation_id: str) -> dict[str, Any] | None:
        client = get_supabase()

        if client is None:
            return None

        response = (
            client.table("organization_invitations")
            .update({"status": "revoked"})
            .eq("id", invitation_id)
            .eq("status", "pending")
            .execute()
        )

        return first_row(response.data)

    # ------------------------------------------------------------------
    # Auth directory lookup
    # ------------------------------------------------------------------

    def find_user_by_email(self, email: str) -> dict[str, Any] | None:
        """Resolve an existing auth user by email, or ``None``.

        Uses the admin auth API (service-role only, never exposed to the
        browser). Returns a plain dict so callers stay decoupled from the
        Supabase SDK types.
        """
        client = get_supabase()

        if client is None:
            return None

        target = email.strip().lower()

        try:
            page = 1
            while page <= 20:  # bounded scan, ~20k users
                response = client.auth.admin.list_users(page=page, per_page=1000)
                users = getattr(response, "users", response) or []

                for user in users:
                    user_email = (getattr(user, "email", None) or "").lower()
                    if user_email == target:
                        return {
                            "id": str(getattr(user, "id", "")),
                            "email": user_email,
                        }

                if len(users) < 1000:
                    break
                page += 1
        except Exception:  # pragma: no cover - network/permission failure
            return None

        return None
