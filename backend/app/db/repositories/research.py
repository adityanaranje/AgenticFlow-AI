from typing import Any

from app.db.supabase import get_supabase

class ResearchRepository:
    """Repository for research runs."""

    def create(
        self,
        data: dict[str, Any],
    ) -> dict[str, Any] | None:
        client = get_supabase()

        if client is None:
            return None

        response = (
            client.table("research_runs")
            .insert(data)
            .select("*")
            .single()
            .execute()
        )

        return response.data

    def get_by_id(
        self,
        research_run_id: str,
        organization_id: str,
    ) -> dict[str, Any] | None:
        client = get_supabase()

        if client is None:
            return None

        response = (
            client.table("research_runs")
            .select("*")
            .eq("id", research_run_id)
            .eq("organization_id", organization_id)
            .maybe_single()
            .execute()
        )

        return response.data

    def list_for_organization(
        self,
        organization_id: str,
    ) -> list[dict[str, Any]]:
        client = get_supabase()

        if client is None:
            return []

        response = (
            client.table("research_runs")
            .select("*")
            .eq("organization_id", organization_id)
            .order("created_at", desc=True)
            .execute()
        )

        return response.data or []

    def update_state(
        self,
        research_run_id: str,
        organization_id: str,
        status: str,
        graph_state: dict[str, Any],
        error: str | None = None,
    ) -> dict[str, Any] | None:
        client = get_supabase()

        if client is None:
            return None

        payload: dict[str, Any] = {
            "status": status,
            "graph_state": graph_state,
        }

        if error is not None:
            payload["error"] = error

        response = (
            client.table("research_runs")
            .update(payload)
            .eq("id", research_run_id)
            .eq("organization_id", organization_id)
            .select("*")
            .maybe_single()
            .execute()
        )

        return response.data