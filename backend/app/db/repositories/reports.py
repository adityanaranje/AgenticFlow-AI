"""Repository for reports + report sources (Phase 5)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from app.db.supabase import get_supabase


class ReportRepository:
    def create(
        self,
        *,
        research_run_id: str,
        organization_id: str,
        title: str,
        content: str,
        summary: str | None = None,
        confidence: float | None = None,
        sections: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        client = get_supabase()
        if client is None:
            return None
        row = {
            "id": str(uuid.uuid4()),
            "research_run_id": research_run_id,
            "organization_id": organization_id,
            "title": title,
            "content": content,
            "summary": summary,
            "confidence": confidence,
            "sections": sections or {},
            "status": "ready",
        }
        response = client.table("reports").insert(row).select("*").single().execute()
        return response.data or row

    def get(self, report_id: str, organization_id: str) -> dict[str, Any] | None:
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
        return response.data

    def list_for_org(self, organization_id: str) -> list[dict[str, Any]]:
        client = get_supabase()
        if client is None:
            return []
        response = (
            client.table("reports")
            .select("id, research_run_id, title, summary, confidence, created_at, status")
            .eq("organization_id", organization_id)
            .order("created_at", desc=True)
            .limit(200)
            .execute()
        )
        return response.data or []

    def delete(self, report_id: str, organization_id: str) -> bool:
        client = get_supabase()
        if client is None:
            return False
        resp = (
            client.table("reports").delete().eq("id", report_id).eq("organization_id", organization_id).execute()
        )
        return bool(resp.data)

    # ---- report sources ----
    def create_source(self, data: dict[str, Any]) -> dict[str, Any] | None:
        client = get_supabase()
        if client is None:
            return None
        row = dict(data)
        row.setdefault("id", str(uuid.uuid4()))
        resp = client.table("report_sources").insert(row).select("*").single().execute()
        return resp.data or row

    def list_sources(self, report_id: str) -> list[dict[str, Any]]:
        client = get_supabase()
        if client is None:
            return []
        resp = (
            client.table("report_sources").select("*").eq("report_id", report_id).order("created_at").execute()
        )
        return resp.data or []


class EvaluationRepository:
    def create_run(
        self,
        *,
        organization_id: str,
        report_id: str | None = None,
        eval_type: str = "report",
    ) -> dict[str, Any] | None:
        client = get_supabase()
        if client is None:
            return None
        row = {
            "id": str(uuid.uuid4()),
            "organization_id": organization_id,
            "report_id": report_id,
            "type": eval_type,
            "dataset": "report-evaluation",
            "status": "running",
            "summary": {},
        }
        resp = client.table("evaluation_runs").insert(row).select("*").single().execute()
        return resp.data or row

    def complete_run(self, run_id: str, summary: dict[str, Any]) -> dict[str, Any] | None:
        client = get_supabase()
        if client is None:
            return None
        resp = (
            client.table("evaluation_runs")
            .update(
                {
                    "status": "completed",
                    "summary": summary,
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            .eq("id", run_id)
            .select("*")
            .single()
            .execute()
        )
        return resp.data

    def create_result(
        self, *, run_id: str, test_case: str, metric: str, score: float | None,
        expected: Any = None, actual: Any = None, metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        client = get_supabase()
        if client is None:
            return None
        row = {
            "evaluation_run_id": run_id,
            "test_case": test_case,
            "metric": metric,
            "score": score,
            "expected": expected,
            "actual": actual,
            "metadata": metadata or {},
        }
        resp = client.table("evaluation_results").insert(row).select("*").single().execute()
        return resp.data or row

    def list_results(self, run_id: str) -> list[dict[str, Any]]:
        client = get_supabase()
        if client is None:
            return []
        resp = (
            client.table("evaluation_results")
            .select("*")
            .eq("evaluation_run_id", run_id)
            .order("created_at")
            .execute()
        )
        return resp.data or []

    def list_runs(self, organization_id: str) -> list[dict[str, Any]]:
        client = get_supabase()
        if client is None:
            return []
        resp = (
            client.table("evaluation_runs")
            .select("id, report_id, type, dataset, status, summary, created_at, completed_at")
            .eq("organization_id", organization_id)
            .order("created_at", desc=True)
            .limit(200)
            .execute()
        )
        return resp.data or []

    def get_run(self, run_id: str, organization_id: str) -> dict[str, Any] | None:
        client = get_supabase()
        if client is None:
            return None
        resp = (
            client.table("evaluation_runs")
            .select("*")
            .eq("id", run_id)
            .eq("organization_id", organization_id)
            .maybe_single()
            .execute()
        )
        return resp.data
