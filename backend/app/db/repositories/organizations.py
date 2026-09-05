from typing import Any
from app.db.supabase import get_supabase

class OrganizationRepository:
    """Repository for organization operations."""

    def create(self, name: str, slug: str) -> dict[str, Any] | None:
        client = get_supabase()

        if client is None:
            return None

        response = client.rpc(
            "create_organization",
            {
                "organization_name":name,
                "organization_slug":slug,
            },
        ).execute()

        return response.data()

    def get_for_user(self, user_id: str) -> list[dict[str,Any]]:
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

    def get_member(self, organization_id: str,) -> list[dict[str, Any]]:
        client = get_supabase()

        if client is None:
            return []

        response = (
            client.table("organization_members")
            .select(
                """
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
            )
            .eq("organization_id", organization_id)
            .execute()
        )

        return response.data or []