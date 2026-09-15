"""Repository for reports + report sources (Phase 5)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from app.db.repositories import first_row
from app.db.supabase import get_supabase
from app.core.logging import get_logger

logger = get_logger(__name__)


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
        response = client.table("reports").insert(row).select("*").execute()
        return first_row(response.data) or row

    def get(self, report_id: str, organization_id: str) -> dict[str, Any] | None:
        client = get_supabase()
        if client is None:
            return None
        response = (
            client.table("reports")
            .select("*")
            .eq("id", report_id)
            .eq("organization_id", organization_id)
            .limit(1)
            .execute()
        )
        return first_row(response.data)

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
        """Insert one report source row.

        If the insert fails because ``document_id`` or ``chunk_id`` references
        a row that no longer exists (stale FK), the insert is retried with
        those columns set to ``NULL`` so the citation metadata is still stored.
        """
        client = get_supabase()
        if client is None:
            return None
        row = dict(data)
        row.setdefault("id", str(uuid.uuid4()))
        try:
            resp = client.table("report_sources").insert(row).select("*").execute()
            return first_row(resp.data) or row
        except Exception:
            # FK violation from a stale document_id / chunk_id reference.
            # Strip the foreign-key columns and retry.
            logger.debug(
                "report_sources insert failed; retrying with NULL document_id/chunk_id.",
                exc_info=True,
            )
            safe = dict(row)
            safe["document_id"] = None
            safe["chunk_id"] = None
            try:
                resp = client.table("report_sources").insert(safe).select("*").execute()
                return first_row(resp.data) or safe
            except Exception:
                logger.warning("report_sources insert failed even with NULL FKs; skipping.")
                return None

    def create_sources(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Insert a batch of source rows in one request.

        A report cites one source per grounded citation; inserting them one
        at a time cost a round trip each (see DocumentRepository.create_chunks
        for the same fix on document chunks).

        When the bulk insert fails (FK violation from stale chunk/document
        references), each row is retried individually via :meth:`create_source`
        which auto-strips stale FKs.
        """
        if not rows:
            return []

        client = get_supabase()

        if client is None:
            return []

        payload = []
        for row in rows:
            item = dict(row)
            item.setdefault("id", str(uuid.uuid4()))
            payload.append(item)

        try:
            resp = client.table("report_sources").insert(payload).select("id").execute()
            return resp.data or payload
        except Exception:
            logger.warning(
                "Bulk report_sources insert failed (%d rows); retrying row-by-row.",
                len(payload),
                exc_info=True,
            )
            results = []
            for row in payload:
                result = self.create_source(row)
                if result is not None:
                    results.append(result)
            return results

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
        resp = client.table("evaluation_runs").insert(row).select("*").execute()
        return first_row(resp.data) or row

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
            .execute()
        )
        return first_row(resp.data)

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
        resp = client.table("evaluation_results").insert(row).select("*").execute()
        return first_row(resp.data) or row

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
            .limit(1)
            .execute()
        )
        return first_row(resp.data)
