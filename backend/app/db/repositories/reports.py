from typing import Any

from app.db.supabase import get_supabase

class ReportRepository:
    """Repository for reports and citations."""

    def create(
        self,
        data: dict[str, Any],
    ) -> dict[str, Any] | None:
        client = get_supabase()

        if client is None:
            return None

        response = (
            client.table("reports")
            .insert(data)
            .select("*")
            .single()
            .execute()
        )

        return response.data

    def get_by_id(
        self,
        report_id: str,
        organization_id: str,
    ) -> dict[str, Any] | None:
        client = get_supabase()

        if client is None:
            return None

        response = (
            client.table("reports")
            .select("*")
            .eq("id", report_id)
            .eq("organization_id", organization_id)
            .maybe_single()
            .execute()
        )

        if response.data is None:
            return None

        return response.data

    def list_for_organization(
        self,
        organization_id: str,
    ) -> list[dict[str, Any]]:
        client = get_supabase()

        if client is None:
            return []

        response = (
            client.table("reports")
            .select("*")
            .eq("organization_id", organization_id)
            .order("created_at", desc=True)
            .execute()
        )

        return response.data or []

    def create_source(
        self,
        data: dict[str, Any],
    ) -> dict[str, Any] | None:
        client = get_supabase()

        if client is None:
            return None

        response = (
            client.table("report_sources")
            .insert(data)
            .select("*")
            .single()
            .execute()
        )

        return response.data

    def list_sources(
        self,
        report_id: str,
    ) -> list[dict[str, Any]]:
        client = get_supabase()

        if client is None:
            return []

        response = (
            client.table("report_sources")
            .select("*")
            .eq("report_id", report_id)
            .order("created_at")
            .execute()
        )

        return response.data or []
