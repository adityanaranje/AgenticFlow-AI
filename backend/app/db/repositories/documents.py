from typing import Any

from app.db.supabase import get_supabase

class DocumentRepository:
    """Repository for document metadata."""
    def create(
        self,
        data: dict[str, Any],
    ) -> dict[str, Any] | None:
        client = get_supabase()

        if client is None:
            return None

        response = (
            client.table("documents")
            .insert(data)
            .select("*")
            .single()
            .execute()
        )

        return response.data

    def get_by_id(
        self,
        document_id: str,
        organization_id: str,
    ) -> dict[str, Any] | None:
        client = get_supabase()

        if client is None:
            return None

        response = (
            client.table("documents")
            .select("*")
            .eq("id", document_id)
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
            client.table("documents")
            .select("*")
            .eq("organization_id", organization_id)
            .order("created_at", desc=True)
            .execute()
        )

        return response.data or []

    def update_status(
        self,
        document_id: str,
        organization_id: str,
        status: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        client = get_supabase()

        if client is None:
            return None

        payload: dict[str, Any] = {
            "status": status,
        }

        if metadata is not None:
            payload["metadata"] = metadata

        response = (
            client.table("documents")
            .update(payload)
            .eq("id", document_id)
            .eq("organization_id", organization_id)
            .select("*")
            .maybe_single()
            .execute()
        )

        return response.data

    def create_chunk(
        self,
        data: dict[str, Any],
    ) -> dict[str, Any] | None:
        client = get_supabase()

        if client is None:
            return None

        response = (
            client.table("document_chunks")
            .insert(data)
            .select("*")
            .single()
            .execute()
        )

        return response.data

    def list_chunks(
        self,
        document_id: str,
        organization_id: str,
    ) -> list[dict[str, Any]]:
        client = get_supabase()

        if client is None:
            return []

        response = (
            client.table("document_chunks")
            .select("*")
            .eq("document_id", document_id)
            .eq("organization_id", organization_id)
            .order("chunk_index")
            .execute()
        )

        return response.data or []
