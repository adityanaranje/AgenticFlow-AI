"""Repository for research runs (Phase 5)."""

from __future__ import annotations

import uuid
from typing import Any

from app.db.repositories import first_row
from app.db.supabase import get_supabase


class ResearchRepository:
    def create(
        self,
        *,
        organization_id: str,
        user_id: str,
        question: str,
        config: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        client = get_supabase()
        if client is None:
            return None
        row = {
            "id": str(uuid.uuid4()),
            "organization_id": organization_id,
            "user_id": user_id,
            "question": question,
            "status": "queued",
            "config": config or {},
            "graph_state": {},
        }
        response = client.table("research_runs").insert(row).select("*").execute()
        return first_row(response.data) or row

    def get(self, research_id: str, organization_id: str) -> dict[str, Any] | None:
        client = get_supabase()
        if client is None:
            return None
        response = (
            client.table("research_runs")
            .select("*")
            .eq("id", research_id)
            .eq("organization_id", organization_id)
            .limit(1)
            .execute()
        )
        return first_row(response.data)

    def get_any(self, research_id: str) -> dict[str, Any] | None:
        client = get_supabase()
        if client is None:
            return None
        response = (
            client.table("research_runs").select("*").eq("id", research_id).limit(1).execute()
        )
        return first_row(response.data)

    def list_for_org(self, organization_id: str) -> list[dict[str, Any]]:
        client = get_supabase()
        if client is None:
            return []
        response = (
            client.table("research_runs")
            .select("id, organization_id, user_id, question, status, error, created_at, started_at, completed_at, config")
            .eq("organization_id", organization_id)
            .order("created_at", desc=True)
            .limit(200)
            .execute()
        )
        return response.data or []

    def update(self, research_id: str, organization_id: str, fields: dict[str, Any]) -> dict[str, Any] | None:
        client = get_supabase()
        if client is None:
            return None
        if not fields:
            return None
        response = (
            client.table("research_runs")
            .update(fields)
            .eq("id", research_id)
            .eq("organization_id", organization_id)
            .select("*")
            .execute()
        )
        return first_row(response.data)

    def set_status(self, research_id: str, organization_id: str, status: str, **extra) -> None:
        fields = {"status": status, **extra}
        self.update(research_id, organization_id, fields)
