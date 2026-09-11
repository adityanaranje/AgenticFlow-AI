from typing import Any

from app.db.repositories import first_row
from app.db.supabase import get_supabase

class UserRepository:
    """Repository for user profile operations."""

    def get_profile(self, user_id: str) -> dict[str, Any] | None:
        client = get_supabase()

        if client is None:
            return None

        response = (
            client.table("profiles")
            .select("*")
            .eq("id", user_id)
            .limit(1)
            .execute()
        )

        return first_row(response.data)

    def update_profile(self, user_id: str, data: dict[str, Any] | None):
        client = get_supabase()

        if client is None:
            return None

        response = (
            client.table("profiles")
            .update(data)
            .eq("id", user_id)
            .select("*")
            .execute()
        )

        return first_row(response.data)
